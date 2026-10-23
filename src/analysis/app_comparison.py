"""Deterministic comparison statistics over saved reviews; no inferred labels."""

import pandas as pd

COUNTS = ["n", "score_sum", "low", "five", "replied"] + [f"stars_{s}" for s in range(1, 6)]
FREQUENCIES = {"Daily": "D", "Weekly": "W-SUN", "Monthly": "M"}
METRICS = {
    "Average rating": ("avg_score", ".2f", [1, 5]),
    "1–2 star share": ("low_share", ".1%", [0, 1]),
    "Saved review count": ("n", ",.0f", None),
    "Developer reply rate": ("reply_share", ".1%", [0, 1]),
}


def _rates(frame):
    out = frame.copy()
    denominator = out["n"].where(out["n"].gt(0))
    out["avg_score"] = out["score_sum"] / denominator
    out["low_share"] = out["low"] / denominator
    out["five_share"] = out["five"] / denominator
    out["reply_share"] = out["replied"] / denominator
    return out


def compare_reviews(daily, packages, start, end, frequency="Weekly"):
    """Inclusive UTC days; weight by reviews, preserve gaps and empty apps.

    Calendar buckets are clipped to the requested range before aggregation.
    Empty buckets are unknown coverage, not zero activity. Summary counts may be
    zero, but no-data rates remain null. Line segments never bridge empty buckets.
    """
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if end < start:
        raise ValueError("End date must be on or after start date.")
    freq = FREQUENCIES[frequency]
    data = daily.copy()
    data["day"] = pd.to_datetime(data["day"])
    data = data[data["package_id"].isin(packages) & data["day"].between(start, end)]
    totals = data.groupby("package_id")[COUNTS].sum().reindex(packages, fill_value=0)
    summary = _rates(totals).reset_index()
    periods = pd.period_range(start, end, freq=freq).start_time
    data["period"] = data["day"].dt.to_period(freq).dt.start_time
    index = pd.MultiIndex.from_product([packages, periods], names=["package_id", "period"])
    trend = data.groupby(["package_id", "period"])[COUNTS].sum().reindex(index)
    trend = _rates(trend).reset_index()
    trend["segment"] = trend.groupby("package_id")["n"].transform(lambda s: s.isna().cumsum())
    trend["line_id"] = trend["package_id"] + ":" + trend["segment"].astype(str)
    trend["period_end"] = trend["period"].dt.to_period(freq).dt.end_time.dt.normalize().clip(upper=end)
    trend["period_start"] = trend["period"].clip(lower=start)
    distribution = summary[["package_id", "n"] + [f"stars_{s}" for s in range(1, 6)]].melt(
        id_vars=["package_id", "n"], var_name="rating", value_name="reviews")
    distribution["rating"] = distribution["rating"].str[-1].astype(int)
    distribution["share"] = distribution["reviews"] / distribution["n"].where(distribution["n"].gt(0))
    return summary, trend, distribution
