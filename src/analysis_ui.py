"""Streamlit rendering for the Analysis tab. Charts only — math lives in
analysis.review_analytics so it stays unit-testable."""

import altair as alt
import pandas as pd
import streamlit as st

from analysis.review_analytics import (
    prepare, volume_rating_by_period, detect_spikes, lang_share_by_period,
    version_timeline, spike_details,
)

_FREQ_LABELS = {"Weekly": "W", "Monthly": "ME"}


def render_analysis_tab(raw_df: pd.DataFrame, pkg: str) -> None:
    df = prepare(raw_df)
    if len(df) < 100:
        st.info("Need at least ~100 reviews with dates for meaningful analysis — crawl more first.")
        return

    st.caption(
        "Review **language** is used as the market proxy — Google Play does not "
        "expose a reviewer's real country. Crawl more languages for wider market coverage."
    )
    # Monthly default: multi-year datasets are noise at weekly granularity
    freq_label = st.radio("Granularity", list(_FREQ_LABELS), index=1, horizontal=True)
    freq = _FREQ_LABELS[freq_label]

    # --- Volume + rating over time, spikes flagged ---
    st.subheader("Review volume & rating over time")
    st.caption(
        "🟦 light bars = review volume · 🟥 red bars = volume spike (≥2× rolling baseline) · "
        "➖ purple line = average rating"
    )
    vol = detect_spikes(volume_rating_by_period(df, freq))
    base = alt.Chart(vol).encode(x=alt.X("period:T", title=None))
    bars = base.mark_bar(opacity=0.7).encode(
        y=alt.Y("n:Q", title="reviews / period"),
        color=alt.condition(alt.datum.is_spike, alt.value("#DC2626"), alt.value("#A5B4FC")),
        tooltip=["period:T", "n:Q", alt.Tooltip("avg_score:Q", format=".2f"), "tone:N"],
    )
    line = base.mark_line(color="#7C3AED", strokeWidth=2.5).encode(
        y=alt.Y("avg_score:Q", title="avg rating", scale=alt.Scale(domain=[1, 5])),
    )
    st.altair_chart(
        alt.layer(bars, line).resolve_scale(y="independent").properties(height=280),
        use_container_width=True,
    )

    # --- Spike explanations: the campaign/backlash view ---
    spikes = spike_details(df, vol, freq)
    if spikes:
        shown = min(10, len(spikes))
        st.subheader(f"Spike windows — latest {shown} of {len(spikes)}")
        # Word badges so the collapsed list is scannable without expanding
        tone_badge = {"positive": "📈 Campaign?", "negative": "🔥 Backlash?", "mixed": "❓ Organic/mixed"}
        for s in reversed(spikes[-shown:]):
            label = (
                f"{tone_badge.get(s['tone'], s['tone'])} · {s['period']:%Y-%m-%d} — "
                f"{s['n']:,} reviews ({s['n'] / max(s['baseline'], 1):.1f}× baseline), "
                f"avg {s['avg_score']:.2f}"
            )
            with st.expander(label):
                verdict = {
                    "positive": "Volume surge with better-than-usual ratings — likely a campaign, feature launch, or store placement push.",
                    "negative": "Volume surge with worse-than-usual ratings — likely a backlash event (bad update, policy change, outage).",
                    "mixed": "Volume surge with typical ratings — organic growth or mixed event.",
                }[s["tone"]]
                st.write(verdict)
                cols = st.columns(3)
                cols[0].markdown(
                    "**Markets (lang)**\n\n"
                    + ("\n".join(f"- {k} — {int(v):,}" for k, v in s["langs"].items()) or "—")
                )
                cols[1].markdown(
                    "**Versions first seen**\n\n"
                    + ("\n".join(f"- {v}" for v in s["new_versions"]) or "—")
                )
                cols[2].markdown(
                    "**Top phrases**\n\n"
                    + ("\n".join(f"- {p}" for p, _ in s["bigrams"][:6]) or "—")
                )

    # --- Market mix over time ---
    st.subheader("Market mix over time (language share)")
    share = lang_share_by_period(df, freq)
    normalized = st.toggle("Show as % share", value=True)
    y = (
        alt.Y("share:Q", title="share", axis=alt.Axis(format="%"), stack="normalize")
        if normalized else alt.Y("n:Q", title="reviews", stack=True)
    )
    st.altair_chart(
        alt.Chart(share).mark_area().encode(
            x=alt.X("period:T", title=None), y=y,
            color=alt.Color("lang:N", title="lang"),
            tooltip=["period:T", "lang:N", "n:Q", alt.Tooltip("share:Q", format=".0%")],
        ).properties(height=240),
        use_container_width=True,
    )
    st.caption(
        "A language's share climbing = that market is being pushed (or reacting). "
        "Only crawled languages appear — absence here can mean 'not crawled', not 'no users'."
    )

    # --- Version timeline ---
    st.subheader("Rating by app version (release order)")
    vt = version_timeline(df)
    if not vt.empty:
        st.altair_chart(
            alt.Chart(vt).mark_circle().encode(
                x=alt.X("first_seen:T", title="version first seen in reviews"),
                y=alt.Y("avg_score:Q", title="avg ⭐", scale=alt.Scale(domain=[1, 5])),
                size=alt.Size("n:Q", title="reviews", scale=alt.Scale(range=[30, 600])),
                color=alt.Color("avg_score:Q", scale=alt.Scale(scheme="redyellowgreen", domain=[1, 5]), legend=None),
                tooltip=["app_version:N", "first_seen:T", "n:Q", alt.Tooltip("avg_score:Q", format=".2f")],
            ).properties(height=240),
            use_container_width=True,
        )
        worst = vt.nsmallest(3, "avg_score")[["app_version", "avg_score", "n"]]
        st.caption(
            "Worst versions: " + ", ".join(
                f"{r.app_version} ({r.avg_score:.2f}⭐, n={int(r.n)})" for r in worst.itertuples()
            )
        )
    else:
        st.info("No app_version data yet — versions are stored for reviews crawled after the schema upgrade.")

    # --- Reply rate ---
    replied = (df["reply_content"].fillna("") != "").sum()
    low = df[df["score"] <= 2]
    low_replied = (low["reply_content"].fillna("") != "").sum()
    st.subheader("Developer engagement")
    c1, c2, c3 = st.columns(3)
    c1.metric("Reply rate (all)", f"{replied / len(df) * 100:.1f}%")
    c2.metric("Reply rate (1-2⭐)", f"{low_replied / max(len(low), 1) * 100:.1f}%")
    c3.metric("1-2⭐ share", f"{len(low) / len(df) * 100:.0f}%")
