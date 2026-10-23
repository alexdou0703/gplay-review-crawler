"""Read-only comparison workspace, independent of the single-app selection."""

from datetime import timedelta

import pandas as pd
import streamlit as st

from analysis.app_comparison import compare_reviews, FREQUENCIES, METRICS
from comparison_charts import APP_COLORS, comparison_trend, comparison_distribution
from storage.comparison_store import comparison_snapshot
from storage.sqlite_store import latest_package_job


def _app_colors(packages):
    mapping = st.session_state.setdefault("compare_colors", {})
    selected = {}
    for pkg in packages:
        if mapping.get(pkg) in APP_COLORS and mapping[pkg] not in selected.values():
            selected[pkg] = mapping[pkg]
    for pkg in packages:
        if pkg not in selected:
            selected[pkg] = next(c for c in APP_COLORS if c not in selected.values())
    mapping.update(selected)
    return selected


def render_comparison(db_path, entries):
    st.subheader("Compare apps")
    st.caption("Compare ratings and review trends across 2–5 apps in your saved library.")
    names = dict(entries)
    if len(names) < 2:
        st.info("Save reviews for at least two apps in Crawl to start comparing.")
        return
    labels = {p: f"{name} · {p}" for p, name in names.items()}
    if "compare_apps" in st.session_state:
        st.session_state.compare_apps = [p for p in st.session_state.compare_apps if p in names][:5]
    applied = st.session_state.get("compare_applied")
    if applied and any(p not in names for p in applied["packages"]):
        st.session_state.pop("compare_applied", None)
        applied = None
        st.info("An app was removed. Choose at least two available apps and compare again.")
    default_packages = list(names)[:2]
    if "compare_apps" not in st.session_state:
        st.session_state.compare_apps = applied["packages"] if applied else default_packages
    if "compare_frequency" not in st.session_state:
        st.session_state.compare_frequency = applied["frequency"] if applied else "Weekly"
    # Initialize dates from observed data once. Later edits stay under user control.
    if "compare_dates" not in st.session_state:
        if applied:
            st.session_state.compare_dates = applied["dates"]
        else:
            _, initial_coverage = comparison_snapshot(default_packages, db_path)
            observed = pd.to_datetime(initial_coverage["last_day"], errors="coerce").max()
            end = observed.date() if pd.notna(observed) else pd.Timestamp.now(tz="UTC").date()
            st.session_state.compare_dates = (end - timedelta(days=89), end)
    with st.form("compare_form"):
        selected = st.multiselect("Apps to compare", list(names),
                                  format_func=labels.get, max_selections=5, key="compare_apps")
        date_col, frequency_col = st.columns([3, 1])
        with date_col:
            dates = st.date_input("Review date range (UTC)", key="compare_dates")
        with frequency_col:
            frequency = st.selectbox("Group by", list(FREQUENCIES), key="compare_frequency")
        submitted = st.form_submit_button("Compare", type="primary")
    if submitted:
        st.session_state.pop("compare_applied", None)
        applied = None
        if not 2 <= len(selected) <= 5:
            st.warning("Choose between 2 and 5 apps to compare.")
            return
        if len(dates) != 2 or dates[1] < dates[0]:
            st.warning("Choose both a start and end date.")
            return
        buckets = len(pd.period_range(dates[0], dates[1], freq=FREQUENCIES[frequency]))
        if buckets > 500:
            st.warning("This range has more than 500 periods. Choose Weekly or Monthly, or shorten the date range.")
            return
        applied = {"packages": list(selected), "dates": dates, "frequency": frequency}
        st.session_state.compare_applied = applied
    if not applied:
        st.info("Choose your apps and date range, then press Compare.")
        return
    packages, dates, frequency = applied["packages"], applied["dates"], applied["frequency"]
    selected_names = [names[p] for p in packages]
    selected_labels = {p: names[p] if selected_names.count(names[p]) == 1 else labels[p] for p in packages}
    heading, refresh = st.columns([4, 1], vertical_alignment="bottom")
    with heading:
        st.markdown(f"**{dates[0]:%d %b %Y} – {dates[1]:%d %b %Y} · {frequency} · {len(packages)} apps**")
    refresh.button("Refresh data", key="compare_refresh", help="Reload saved reviews without starting a crawl")
    daily, coverage = comparison_snapshot(packages, db_path)
    summary, trend, distribution = compare_reviews(daily, packages, *dates, frequency)
    st.caption("Saved review samples only — not store-wide ratings, downloads or market share. "
               "Crawl limits and query languages may differ. Gaps mean no saved reviews in that period; completeness is unknown.")
    no_data = summary.loc[summary["n"].eq(0), "package_id"].tolist()
    if no_data:
        st.info("No rated, dated reviews in this range for: " + "; ".join(selected_labels[p] for p in no_data) + ". Try a wider date range.")
    if summary["n"].gt(0).any():
        with st.container(border=True):
            st.subheader("Compare trends")
            metric = st.selectbox("Metric", list(METRICS), key="compare_metric")
            st.altair_chart(comparison_trend(trend, selected_labels, _app_colors(packages), metric), use_container_width=True)
            st.caption("Each point summarizes that calendar period within the selected dates. Hover to compare all apps and sample counts.")
        with st.container(border=True):
            st.subheader("Rating distribution")
            st.altair_chart(comparison_distribution(distribution, selected_labels), use_container_width=True)
        with st.expander("Trend data"):
            period_table = trend[["package_id", "period_start", "period_end", "n", "avg_score", "low_share", "reply_share"]].copy()
            period_table["package_id"] = period_table["package_id"].map(selected_labels)
            period_table["low_share"] *= 100
            period_table["reply_share"] *= 100
            st.dataframe(period_table.rename(columns={"package_id": "App", "period_start": "From (UTC)",
                "period_end": "Through (UTC)", "n": "Reviews", "avg_score": "Average rating",
                "low_share": "1–2 star %", "reply_share": "Reply %"}), hide_index=True, use_container_width=True)
    st.subheader("Comparison summary")
    table = summary[["package_id", "n", "avg_score", "low_share", "five_share", "reply_share"]].copy()
    table.insert(0, "App", table["package_id"].map(names))
    for col in ["low_share", "five_share", "reply_share"]:
        table[col] *= 100
    st.dataframe(table.rename(columns={"package_id": "Package ID", "n": "Reviews in range", "avg_score": "Average rating",
        "low_share": "1–2 star %", "five_share": "5 star %", "reply_share": "Reply %"}),
        hide_index=True, use_container_width=True, row_height=52,
        column_config={"Average rating": st.column_config.NumberColumn(format="%.2f"),
                       **{c: st.column_config.NumberColumn(format="%.1f%%") for c in ["1–2 star %", "5 star %", "Reply %"]}})
    st.subheader("Data coverage")
    coverage = coverage.set_index("package_id").reindex(packages).reset_index()
    coverage.insert(0, "App", coverage["package_id"].map(names))
    coverage["excluded"] = coverage["saved"] - coverage["usable"]
    coverage["Crawl status"] = [(latest_package_job(p, db_path) or {}).get("status", "No recorded crawl") for p in packages]
    st.dataframe(coverage.rename(columns={"package_id": "Package ID", "saved": "All saved reviews", "usable": "Rated & dated",
        "first_day": "Oldest observed date", "last_day": "Newest observed date", "last_saved": "Last saved (UTC)",
        "crawl_languages": "Query languages", "crawl_stores": "Query stores", "excluded": "Excluded: invalid date/rating"}),
        hide_index=True, use_container_width=True, row_height=52)
    st.caption("Observed dates do not guarantee complete coverage. Query languages/stores describe crawl requests, not verified reviewer language or country. "
               "Metrics use reviews with a valid date and a 1–5 star rating; excluded rows are listed above.")
