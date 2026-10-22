"""Altair chart builders with one visual language and explicit data labels."""

import altair as alt
import pandas as pd

BLUE = "#2563EB"
TEAL = "#087F8C"
AMBER = "#B45309"
LANG_COLORS = ["#2563EB", "#087F8C", "#8B5CF6", "#B45309", "#DB2777", "#4D7C0F", "#475569", "#0369A1", "#9CA3AF"]


def style(chart, height=280):
    return (chart.properties(height=height)
            .configure(background="#FFFFFF", font="Be Vietnam Pro")
            .configure_view(stroke=None)
            .configure_axis(labelColor="#596579", titleColor="#596579", labelFontSize=12,
                            titleFontSize=12, titleFontWeight=400, gridColor="#EDF0F4",
                            domain=False, tickColor="#E3E7EE", labelPadding=8, titlePadding=12)
            .configure_legend(title=None, orient="bottom", labelColor="#596579", labelFontSize=12,
                              symbolType="circle", padding=12))


def _period_labels(data, freq):
    out = data.copy()
    out["period_label"] = out["period"].dt.strftime("%b %Y" if freq == "ME" else "%d %b %y")
    return out


def volume_chart(volume, freq="ME"):
    data = _period_labels(volume, freq)
    base = alt.Chart(data).encode(x=alt.X("period_label:O", title=None, sort=None,
                                         axis=alt.Axis(grid=False, labelAngle=0, labelOverlap="greedy")))
    tooltip = [alt.Tooltip("period:T", title="Period", format="%d %b %Y"),
               alt.Tooltip("n:Q", title="Reviews", format=","),
               alt.Tooltip("avg_score:Q", title="Average rating", format=".2f"),
               alt.Tooltip("is_spike:N", title="Volume spike")]
    bars = base.mark_bar(color="#93B4EE", cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        y=alt.Y("n:Q", title="Reviews", axis=alt.Axis(format="~s")),
        color=alt.condition(alt.datum.is_spike, alt.value(AMBER), alt.value("#93B4EE")),
        tooltip=tooltip,
    )
    line = base.mark_line(color=TEAL, strokeWidth=2.5,
                         point=alt.OverlayMarkDef(color=TEAL, filled=True, size=30)).encode(
        y=alt.Y("avg_score:Q", title="Average rating", scale=alt.Scale(domain=[1, 5]),
                axis=alt.Axis(orient="right", grid=False, values=[1, 2, 3, 4, 5])),
        tooltip=tooltip,
    )
    return style(alt.layer(bars, line).resolve_scale(y="independent"), 320)


def ratings_chart(df):
    counts = df["score"].value_counts().reindex([5, 4, 3, 2, 1], fill_value=0)
    data = pd.DataFrame({"rating": [f"{s} stars" for s in counts.index], "reviews": counts.values})
    data["share"] = data["reviews"] / max(int(data["reviews"].sum()), 1)
    base = alt.Chart(data).encode(y=alt.Y("rating:N", title=None, sort=list(data["rating"])))
    bars = base.mark_bar(color=BLUE, size=22, cornerRadiusEnd=3).encode(
        x=alt.X("reviews:Q", title="Reviews", axis=alt.Axis(tickMinStep=1)),
        tooltip=[alt.Tooltip("rating:N", title="Rating"), alt.Tooltip("reviews:Q", title="Reviews", format=","),
                 alt.Tooltip("share:Q", title="Share", format=".1%")],
    )
    return style(bars, 270)


def language_chart(share, normalized=True, freq="ME"):
    # Fixed domain across periods keeps colors stable within the snapshot.
    languages = sorted(set(share["lang"]) - {"Other"}) + (["Other"] if "Other" in set(share["lang"]) else [])
    y = (alt.Y("share:Q", title="Share of reviews", stack="normalize", axis=alt.Axis(format="%"))
         if normalized else alt.Y("n:Q", title="Reviews", stack="zero"))
    data = _period_labels(share, freq)
    periods = list(data.sort_values("period")["period_label"].drop_duplicates())
    return style(alt.Chart(data).mark_bar().encode(
        x=alt.X("period_label:O", title=None, sort=periods,
                axis=alt.Axis(grid=False, labelAngle=0, labelOverlap="greedy")), y=y,
        color=alt.Color("lang:N", scale=alt.Scale(domain=languages, range=LANG_COLORS),
                        legend=alt.Legend(columns=3, labelLimit=85)),
        order=alt.Order("lang:N", sort="ascending"),
        tooltip=[alt.Tooltip("period:T", title="Period", format="%b %Y"),
                 alt.Tooltip("lang:N", title="Language"), alt.Tooltip("n:Q", title="Reviews", format=","),
                 alt.Tooltip("share:Q", title="Share", format=".1%")],
    ), 270)


def versions_chart(versions):
    return style(alt.Chart(versions).mark_circle(color=BLUE, opacity=.8, stroke="white", strokeWidth=1).encode(
        x=alt.X("first_seen:T", title="First seen in saved reviews", axis=alt.Axis(grid=False)),
        y=alt.Y("avg_score:Q", title="Average rating", scale=alt.Scale(domain=[1, 5]),
                axis=alt.Axis(values=[1, 2, 3, 4, 5])),
        size=alt.Size("n:Q", title="Reviews", scale=alt.Scale(range=[60, 650]),
                      legend=alt.Legend(values=[30, 100, 300], direction="horizontal")),
        tooltip=[alt.Tooltip("app_version:N", title="Version"),
                 alt.Tooltip("first_seen:T", title="First seen", format="%d %b %Y"),
                 alt.Tooltip("n:Q", title="Reviews", format=","),
                 alt.Tooltip("avg_score:Q", title="Average rating", format=".2f")],
    ), 320)
