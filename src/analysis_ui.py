"""Filtered, cached analytics workspace; calculations remain in analysis/."""

import pandas as pd
import streamlit as st

from analysis.review_analytics import (
    prepare, volume_rating_by_period, detect_spikes,
    version_timeline, spike_details, top_language_share,
)
from analysis_charts import volume_chart, ratings_chart, language_chart, versions_chart

_FREQ_LABELS = {"Daily": "D", "Weekly": "W", "Monthly": "ME"}


@st.cache_data(max_entries=32, show_spinner=False)
def _cached_analysis_tables(df: pd.DataFrame, freq: str):
    """Hash the actual filtered rows, so equal-size app snapshots cannot collide."""
    volume = detect_spikes(volume_rating_by_period(df, freq))
    share = top_language_share(df, freq, top_n=8)
    versions = version_timeline(df[df["app_version"].ne("Unknown")])
    return volume, share, versions


@st.cache_data(max_entries=16, show_spinner=False)
def _cached_spikes(df: pd.DataFrame, freq: str):
    return spike_details(df, detect_spikes(volume_rating_by_period(df, freq)), freq)


def filter_analysis(df, dates, languages):
    """Inclusive calendar-date bounds in UTC; an empty language list means all."""
    start = pd.Timestamp(dates[0], tz="UTC")
    end = pd.Timestamp(dates[1], tz="UTC") + pd.Timedelta(days=1)
    mask = df["dt"].ge(start) & df["dt"].lt(end)
    if languages:
        mask &= df["lang"].isin(languages)
    return df.loc[mask].copy()


def render_analysis_tab(raw_df: pd.DataFrame, pkg: str) -> None:
    prepared = prepare(raw_df)
    if prepared.empty:
        st.info("No dated reviews are available yet. Complete or resume a crawl first.")
        return
    first, last = prepared["dt"].min().date(), prepared["dt"].max().date()
    st.subheader("Review analytics")
    st.caption("Explore activity, ratings, and languages in your saved reviews.")
    with st.form(f"analytics_filters_{pkg}"):
        period_col, language_col, interval_col = st.columns([2, 2, 1])
        with period_col:
            dates = st.date_input("Review date range", value=(first, last), min_value=first,
                                  max_value=last, key=f"analytics_dates_{pkg}")
        with language_col:
            languages = st.multiselect("Review languages", sorted(prepared["lang"].unique()),
                                       key=f"analytics_languages_{pkg}", help="Leave empty to include all saved languages.")
        with interval_col:
            freq_label = st.selectbox("Group by", list(_FREQ_LABELS), index=2, key=f"analytics_frequency_{pkg}")
        st.form_submit_button("Apply filters", type="primary")
    if len(dates) != 2:
        st.info("Choose both a start and end date, then apply filters.")
        return
    df = filter_analysis(prepared, dates, languages)
    if df.empty:
        st.info("No saved reviews match these filters. Widen the date range or include more languages.")
        return
    freq = _FREQ_LABELS[freq_label]
    total = len(df)
    replied = int(df["reply_content"].str.strip().ne("").sum())
    low = df[df["score"] <= 2]
    a, b, c, d = st.columns(4)
    a.metric("Dated reviews", f"{total:,}")
    b.metric("Average rating", f"{df['score'].mean():.2f} / 5")
    c.metric("Review languages", f"{df['lang'].nunique():,}")
    d.metric("Developer reply rate", f"{replied / total:.1%}", help=f"{replied:,} replies / {total:,} dated reviews")
    st.caption(f"{dates[0]:%d %b %Y} – {dates[1]:%d %b %Y} · {total:,} of {len(prepared):,} dated reviews · {pkg}")
    if total < 100:
        st.info(f"Small sample: {total:,} dated reviews. These charts describe the saved sample; trends are directional until ~100 reviews.")
    missing_dates = len(raw_df) - len(prepared)
    if missing_dates:
        st.caption(f"{missing_dates:,} duplicate or undated rows are excluded from this analysis.")

    view = st.radio("Analytics view", ["Overview", "Versions", "Signals"], horizontal=True, key=f"analytics_view_{pkg}")
    volume, share, versions = _cached_analysis_tables(df, freq)
    if view == "Overview":
        with st.container(border=True):
            st.subheader("Review activity")
            st.caption("Blue bars: review volume · Teal line: average rating (right axis) · Amber bars: volume spikes")
            st.altair_chart(volume_chart(volume, freq), use_container_width=True)
        left, right = st.columns(2)
        with left, st.container(border=True):
            st.subheader("Rating distribution")
            st.caption("How the selected reviews are rated.")
            st.altair_chart(ratings_chart(df), use_container_width=True)
        with right, st.container(border=True):
            st.subheader("Language mix")
            normalized = st.toggle("Show percentage", value=True, key=f"analytics_share_{pkg}")
            st.altair_chart(language_chart(share, normalized, freq), use_container_width=True)
        st.caption("Language is a market proxy, not reviewer country. Only crawled languages are represented; smaller languages are grouped as Other.")
        with st.expander("Developer engagement"):
            l1, l2 = st.columns(2)
            low_replied = int(low["reply_content"].str.strip().ne("").sum())
            l1.metric("1–2 star share", f"{len(low) / total:.1%}")
            l2.metric("Reply rate · 1–2 stars", f"{low_replied / len(low):.1%}" if len(low) else "—",
                      help="No low-rated reviews means this rate is not available.")
    elif view == "Versions":
        with st.container(border=True):
            st.subheader("Version timeline")
            st.caption("First appearance in the selected reviews, not an official release date. Bubble size shows review count; each version needs at least 30 reviews.")
            if versions.empty:
                st.info("No known app version has 30 reviews in this selection. Widen the date range or collect more reviews.")
            else:
                st.altair_chart(versions_chart(versions), use_container_width=True)
                table = versions.rename(columns={"app_version": "Version", "first_seen": "First seen", "n": "Reviews", "avg_score": "Average rating"})
                table["First seen"] = table["First seen"].dt.strftime("%Y-%m-%d")
                st.dataframe(table, hide_index=True, use_container_width=True,
                             column_config={"Average rating": st.column_config.NumberColumn(format="%.2f")})
    else:
        st.subheader("Unusual review activity")
        st.caption("At least 2× the prior baseline and 30 reviews in a period. These signals describe patterns; they do not establish a cause.")
        spikes = _cached_spikes(df, freq)
        if not spikes:
            st.info("No volume spikes meet the threshold in this selection. A baseline needs enough observed earlier periods.")
        tone_label = {"positive": "Higher ratings", "negative": "Lower ratings", "mixed": "Mixed ratings"}
        for spike in reversed(spikes[-10:]):
            with st.expander(f"{spike['period']:%d %b %Y} · {tone_label[spike['tone']]} · {spike['n']:,} reviews · {spike['n'] / max(spike['baseline'], 1):.1f}× baseline"):
                st.write(f"Average rating: {spike['avg_score']:.2f} / 5. Compare the reviews and app changes before attributing a cause.")
                x, y, z = st.columns(3)
                x.write("Top languages")
                x.write(spike["langs"])
                y.write("Versions first seen")
                y.write(", ".join(spike["new_versions"]) or "No known versions")
                z.write("Common phrases")
                z.write(", ".join(p for p, _ in spike["bigrams"][:6]) or "No common phrases")
        if len(spikes) > 10:
            st.caption(f"Showing the latest 10 of {len(spikes)} spike windows.")
