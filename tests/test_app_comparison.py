"""Comparison statistics reconcile to saved rows and preserve unknown coverage."""

import sqlite3

import pandas as pd
import pytest

from analysis.app_comparison import compare_reviews, METRICS
from comparison_charts import comparison_distribution, comparison_trend
from storage.comparison_store import comparison_snapshot
from storage.sqlite_store import init_db, save_app_name, save_reviews


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "comparison.db")
    init_db(path)
    for package in ["a", "b", "empty", "outside"]:
        save_app_name(package, "Same name", path)
    return path


def save(db, package, scores, day, *, prefix="", reply=""):
    save_reviews([
        {"reviewId": f"{package}-{prefix}-{day}-{i}", "score": score, "at": day,
         "content": "Review", "replyContent": reply, "lang": "en", "country": "us"}
        for i, score in enumerate(scores)
    ], package, db)


def test_snapshot_is_selected_only_deduplicated_and_does_not_load_text(db):
    save(db, "a", [1, 5], "2026-01-01")
    save(db, "b", [3], "2026-01-01")
    save(db, "outside", [1] * 20, "2026-01-01")
    save(db, "a", [1, 5], "2026-01-01")  # Same review IDs update, never double-count.
    daily, coverage = comparison_snapshot(["a", "b", "a"], db)
    assert set(daily.package_id) == {"a", "b"}
    assert set(coverage.package_id) == {"a", "b"}
    assert daily.n.sum() == coverage.saved.sum() == 3
    assert not {"content", "reply_content", "username"}.intersection(daily.columns)


@pytest.mark.parametrize("packages", [[], ["a"], ["a", "a"], list("abcdef")])
def test_snapshot_requires_two_to_five_unique_apps(db, packages):
    with pytest.raises(ValueError, match="2 and 5"):
        comparison_snapshot(packages, db)


def test_snapshot_accepts_five_apps_without_rows(db):
    daily, coverage = comparison_snapshot(list("abcde"), db)
    assert daily.empty and coverage.empty


def test_weighted_means_and_all_share_denominators(db):
    save(db, "a", [1], "2026-01-01", reply="Thanks")
    save(db, "a", [5, 5, 5], "2026-01-02")
    save(db, "b", [2, 3], "2026-01-01", reply="Thanks")
    daily, _ = comparison_snapshot(["a", "b"], db)
    summary, trend, distribution = compare_reviews(daily, ["a", "b"], "2026-01-01", "2026-01-02", "Weekly")
    rows = summary.set_index("package_id")
    assert rows.loc["a", "avg_score"] == 4  # Not the mean of daily means (3).
    assert rows.loc["a", "low_share"] == rows.loc["a", "reply_share"] == .25
    assert rows.loc["a", "five_share"] == .75
    assert rows.loc["b", "avg_score"] == 2.5
    assert rows.loc["b", "low_share"] == .5
    assert rows.loc["b", "reply_share"] == 1
    assert trend.set_index("package_id").loc["a", "avg_score"] == 4
    assert distribution.groupby("package_id").reviews.sum().to_dict() == {"a": 4, "b": 2}
    assert distribution.groupby("package_id").share.sum().to_dict() == {"a": 1, "b": 1}
    assert distribution.loc[distribution.package_id.eq("a") & distribution.rating.eq(5), "reviews"].item() == 3


def test_utc_bounds_include_last_day_and_convert_offsets(db):
    save(db, "a", [1], "2026-01-01T23:59:59Z")
    save(db, "a", [5], "2026-01-02T00:00:00Z")
    save(db, "a", [3], "2026-01-02T06:30:00+07:00")  # Jan 1 UTC.
    save(db, "a", [4], "2025-12-31T23:30:00-02:00")  # Jan 1 UTC.
    daily, _ = comparison_snapshot(["a", "b"], db)
    summary, _, _ = compare_reviews(daily, ["a", "b"], "2026-01-01", "2026-01-01", "Daily")
    row = summary.set_index("package_id").loc["a"]
    assert row.n == 3
    assert row.avg_score == pytest.approx(8 / 3)


def test_invalid_dates_ratings_and_blank_replies_do_not_inflate_statistics(db):
    save(db, "a", [1, 5], "2026-01-01", reply=" \t\n\r ")
    save(db, "a", [4], "2026-01-02", reply="\n Thank you \t")
    save(db, "a", [0, 6, None, 2.5], "2026-01-01", prefix="invalid")
    save(db, "a", [1], "not-a-date")
    daily, coverage = comparison_snapshot(["a", "b"], db)
    assert daily.n.sum() == 3
    assert daily.replied.sum() == 1
    row = coverage.set_index("package_id").loc["a"]
    assert row.saved == 8 and row.usable == 3
    assert row.first_day == "2026-01-01" and row.last_day == "2026-01-02"
    assert row.crawl_languages == "en" and row.crawl_stores == "us"


@pytest.mark.parametrize("invalid_day", ["2026-02-30", "0000-01-01", "9999-12-31", 2461041.5])
def test_non_calendar_or_out_of_bounds_dates_are_excluded_before_pandas(db, invalid_day):
    save(db, "a", [1], invalid_day)
    save(db, "a", [5], "2026-01-01")
    daily, coverage = comparison_snapshot(["a", "b"], db)
    assert daily.day.tolist() == ["2026-01-01"]
    row = coverage.set_index("package_id").loc["a"]
    assert row.saved == 2 and row.usable == 1
    assert row.first_day == row.last_day == "2026-01-01"
    summary, _, _ = compare_reviews(daily, ["a", "b"], "2026-01-01", "2026-01-31", "Monthly")
    assert summary.set_index("package_id").loc["a", "avg_score"] == 5


@pytest.mark.parametrize("frequency", ["Daily", "Weekly", "Monthly"])
def test_empty_snapshot_returns_zero_summary_but_unavailable_rates_and_trends(db, frequency):
    daily, _ = comparison_snapshot(["a", "b"], db)
    summary, trend, distribution = compare_reviews(daily, ["a", "b"], "2026-01-01", "2026-01-31", frequency)
    assert list(summary.package_id) == ["a", "b"]
    assert list(summary.n) == [0, 0]
    assert summary[["avg_score", "low_share", "five_share", "reply_share"]].isna().all().all()
    assert trend[["n", "avg_score", "low_share", "reply_share"]].isna().all().all()
    assert distribution.reviews.eq(0).all() and distribution.share.isna().all()


def test_app_without_rows_in_range_still_has_summary_and_no_fake_zero_rating(db):
    save(db, "a", [4], "2026-01-01")
    save(db, "b", [2], "2025-12-31")
    daily, _ = comparison_snapshot(["a", "b"], db)
    summary, trend, _ = compare_reviews(daily, ["b", "a"], "2026-01-01", "2026-01-03", "Daily")
    assert list(summary.package_id) == ["b", "a"]
    assert summary.iloc[0].n == 0 and pd.isna(summary.iloc[0].avg_score)
    assert trend.loc[trend.package_id.eq("b"), "n"].isna().all()


def test_calendar_week_boundary_and_partial_period_clipping(db):
    save(db, "a", [1], "2026-01-04")  # Sunday, prior calendar week.
    save(db, "a", [5], "2026-01-05")  # Monday, new week.
    save(db, "a", [2], "2026-01-06")  # Must be excluded even in same week.
    daily, _ = comparison_snapshot(["a", "b"], db)
    _, trend, _ = compare_reviews(daily, ["a", "b"], "2026-01-04", "2026-01-05", "Weekly")
    rows = trend[trend.package_id.eq("a")]
    assert list(rows.avg_score) == [1, 5]
    assert list(rows.period_start.dt.strftime("%Y-%m-%d")) == ["2026-01-04", "2026-01-05"]
    assert list(rows.period_end.dt.strftime("%Y-%m-%d")) == ["2026-01-04", "2026-01-05"]


def test_calendar_month_boundary_not_rolling_thirty_days(db):
    save(db, "a", [1], "2026-01-31")
    save(db, "a", [5], "2026-02-01")
    daily, _ = comparison_snapshot(["a", "b"], db)
    _, trend, _ = compare_reviews(daily, ["a", "b"], "2026-01-31", "2026-02-01", "Monthly")
    assert list(trend[trend.package_id.eq("a")].avg_score) == [1, 5]


def test_gaps_break_lines_and_single_observations_remain_points(db):
    save(db, "a", [1], "2026-01-01")
    save(db, "a", [5], "2026-01-03")
    save(db, "b", [3], "2026-01-02")
    daily, _ = comparison_snapshot(["a", "b"], db)
    _, trend, _ = compare_reviews(daily, ["a", "b"], "2026-01-01", "2026-01-03", "Daily")
    rows = trend[trend.package_id.eq("a")].reset_index(drop=True)
    assert pd.isna(rows.loc[1, "n"])
    assert rows.loc[0, "line_id"] != rows.loc[2, "line_id"]
    assert rows.loc[0, "avg_score"] == 1 and rows.loc[2, "avg_score"] == 5


def test_reversed_date_range_is_rejected(db):
    daily, _ = comparison_snapshot(["a", "b"], db)
    with pytest.raises(ValueError, match="End date"):
        compare_reviews(daily, ["a", "b"], "2026-02-01", "2026-01-01")


@pytest.mark.parametrize("metric", list(METRICS))
def test_chart_serialization_has_fixed_axes_safe_hover_fields_and_app_identity(db, metric):
    save(db, "a", [1], "2026-01-01")
    save(db, "a", [5], "2026-01-03")
    save(db, "b", [3], "2026-01-02")
    daily, _ = comparison_snapshot(["a", "b"], db)
    _, trend, distribution = compare_reviews(daily, ["a", "b"], "2026-01-01", "2026-01-03", "Daily")
    labels = {"a": "Same.name · a", "b": "Same.name · b"}
    colors = {"a": "#2563EB", "b": "#087F8C"}
    spec = comparison_trend(trend, labels, colors, metric).to_dict()
    line, point, _, rule = spec["layer"]
    assert line["encoding"]["detail"]["field"] == "line_id"
    assert point["mark"]["type"] == "point"
    assert line["encoding"]["color"]["scale"] == {"domain": list(labels.values()), "range": list(colors.values())}
    domain = METRICS[metric][2]
    if domain:
        assert line["encoding"]["y"]["scale"]["domain"] == domain
    else:
        assert line["encoding"]["y"]["scale"]["zero"] is True
    assert [t["field"] for t in rule["encoding"]["tooltip"]][-2:] == ["app_0", "app_1"]
    hover_rows = next(rows for rows in spec["datasets"].values() if rows and "app_0" in rows[0])
    assert any("no saved reviews" in row["app_0"] for row in hover_rows)
    assert any("reviews" in row["app_1"] for row in hover_rows)
    distribution_spec = comparison_distribution(distribution, labels).to_dict()
    assert distribution_spec["encoding"]["x"]["scale"]["domain"] == [0, 1]
    assert distribution_spec["encoding"]["y"]["sort"] == list(labels.values())


def test_latest_save_is_compared_as_utc_not_lexical_timestamp(db):
    save(db, "a", [1, 2], "2026-01-01")
    with sqlite3.connect(db) as conn:
        ids = [row[0] for row in conn.execute("SELECT review_id FROM reviews ORDER BY review_id")]
        conn.execute("UPDATE reviews SET crawled_at=? WHERE review_id=?", ("2026-01-02T01:00:00+07:00", ids[0]))
        conn.execute("UPDATE reviews SET crawled_at=? WHERE review_id=?", ("2026-01-01T23:00:00Z", ids[1]))
    _, coverage = comparison_snapshot(["a", "b"], db)
    assert coverage.set_index("package_id").loc["a", "last_saved"] == "2026-01-01 23:00:00"
