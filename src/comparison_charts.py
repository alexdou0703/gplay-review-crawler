"""Multi-app charts with shared period hover and explicit missing-data gaps."""

import altair as alt
import pandas as pd

from analysis.app_comparison import METRICS

APP_COLORS = ["#2563EB", "#087F8C", "#8B5CF6", "#B45309", "#DB2777"]
STAR_COLORS = ["#B91C1C", "#D97706", "#94A3B8", "#14B8A6", "#047857"]


def _style(chart, height):
    return (chart.properties(height=height)
            .configure(background="#FFFFFF", font="Be Vietnam Pro")
            .configure_view(stroke=None)
            .configure_axis(labelFontSize=16, titleFontSize=16, labelColor="#596579",
                            titleColor="#596579", gridColor="#EDF0F4", domain=False,
                            labelPadding=8, titlePadding=12)
            .configure_legend(title=None, orient="bottom", labelFontSize=16,
                              labelLimit=220, columns=1, symbolType="circle", padding=16))


def comparison_trend(trend, labels, colors, metric):
    field, fmt, domain = METRICS[metric]
    data = trend.copy()
    data["app"] = data["package_id"].map(labels)
    app_labels = list(labels.values())
    scale = alt.Scale(domain=app_labels, range=[colors[p] for p in labels])
    y = alt.Y(f"{field}:Q", title=metric,
              scale=alt.Scale(domain=domain) if domain else alt.Scale(zero=True),
              axis=alt.Axis(format=".0%" if "share" in field else "~s" if field == "n" else ".1f"))
    base = alt.Chart(data).encode(
        x=alt.X("period_start:T", title="Review date (UTC)", axis=alt.Axis(format="%d %b", labelOverlap="greedy", labelSeparation=12)),
        y=y, color=alt.Color("app:N", scale=scale),
        detail=alt.Detail("line_id:N"), order="period_start:T",
    )
    lines = base.mark_line(strokeWidth=2.5)
    points = base.mark_point(filled=True, size=45).encode(tooltip=[
        alt.Tooltip("app:N", title="App"),
        alt.Tooltip("period_start:T", title="From (UTC)", format="%d %b %Y"),
        alt.Tooltip("period_end:T", title="Through (UTC)", format="%d %b %Y"),
        alt.Tooltip(f"{field}:Q", title=metric, format=fmt),
        alt.Tooltip("n:Q", title="Saved reviews", format=","),
    ])
    # Wide tooltip uses safe field IDs (app names/package IDs may contain dots).
    hover = data[["period_start", "period_end"]].drop_duplicates().sort_values("period_start")
    tips = [alt.Tooltip("period_start:T", title="From (UTC)", format="%d %b %Y"),
            alt.Tooltip("period_end:T", title="Through (UTC)", format="%d %b %Y")]
    for i, (pkg, label) in enumerate(labels.items()):
        rows = data[data["package_id"].eq(pkg)].set_index("period_start")
        def display(row):
            if pd.isna(row[field]):
                return "— (no saved reviews)"
            value = format(row[field], fmt)
            return f"{value} · {int(row['n']):,} reviews"
        values = rows.apply(display, axis=1)
        hover[f"app_{i}"] = hover["period_start"].map(values)
        tips.append(alt.Tooltip(f"app_{i}:N", title=label))
    nearest = alt.selection_point(name="compare_hover", fields=["period_start"], nearest=True,
                                  on="pointerover", clear="pointerout", empty=False)
    selectors = alt.Chart(hover).mark_point(opacity=0).encode(x="period_start:T", tooltip=tips).add_params(nearest)
    rule = alt.Chart(hover).mark_rule(color="#94A3B8").encode(
        x="period_start:T", tooltip=tips,
        opacity=alt.condition(nearest, alt.value(1), alt.value(0)),
    )
    return _style(alt.layer(lines, points, selectors, rule), 400 + len(labels) * 32)


def comparison_distribution(distribution, labels):
    data = distribution.copy()
    data["app"] = data["package_id"].map(labels)
    data["stars"] = data["rating"].astype(str) + " stars"
    return _style(alt.Chart(data).mark_bar(size=28).encode(
        y=alt.Y("app:N", title=None, sort=list(labels.values()), axis=alt.Axis(labelLimit=120)),
        x=alt.X("share:Q", title="Share of saved reviews", stack="zero",
                scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
        color=alt.Color("stars:N", scale=alt.Scale(domain=[f"{i} stars" for i in range(1, 6)], range=STAR_COLORS),
                        legend=alt.Legend(columns=2)),
        order=alt.Order("rating:Q"),
        tooltip=[alt.Tooltip("app:N", title="App"), alt.Tooltip("stars:N", title="Rating"),
                 alt.Tooltip("reviews:Q", title="Reviews", format=","),
                 alt.Tooltip("share:Q", title="Share", format=".1%")],
    ), 220 + len(labels) * 64)
