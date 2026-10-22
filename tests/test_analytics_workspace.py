"""Behavior checks for filtered analytics, charts, and the app library."""

from datetime import date
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from analysis.review_analytics import prepare, spike_details
from analysis_charts import volume_chart, ratings_chart, language_chart, versions_chart
from analysis_ui import _cached_analysis_tables, filter_analysis
from storage.sqlite_store import init_db, save_app_name, save_reviews, app_library_summary


def sample():
    return pd.DataFrame([
        {"review_id": "a", "review_created_at": "2026-01-01T23:59:59Z", "score": 5, "lang": "en", "content": "Useful", "app_version": "1"},
        {"review_id": "b", "review_created_at": "2026-01-02T00:00:00Z", "score": 1, "lang": "vi", "content": "Slow", "app_version": "2"},
        {"review_id": "c", "review_created_at": "2026-01-03T00:00:00Z", "score": 3, "lang": "vi", "content": "Fine"},
    ])


def test_calendar_filter_includes_end_day_and_honors_language():
    df = prepare(sample())
    dates = (date(2026, 1, 1), date(2026, 1, 2))
    assert list(filter_analysis(df, dates, [])["review_id"]) == ["a", "b"]
    assert list(filter_analysis(df, dates, ["vi"])["review_id"]) == ["b"]
    assert filter_analysis(df, dates, ["de"]).empty


def test_analytics_cache_distinguishes_same_size_same_date_datasets():
    first = prepare(sample())
    second = first.assign(score=2)
    a, _, _ = _cached_analysis_tables(first, "ME")
    b, _, _ = _cached_analysis_tables(second, "ME")
    assert a.iloc[0].avg_score == 3
    assert b.iloc[0].avg_score == 2


def test_charts_serialize_small_sample_and_fixed_rating_axis():
    df = prepare(sample())
    volume, share, versions = _cached_analysis_tables(df, "D")
    spec = volume_chart(volume).to_dict()
    assert spec["resolve"]["scale"]["y"] == "independent"
    assert spec["layer"][1]["encoding"]["y"]["scale"]["domain"] == [1, 5]
    assert ratings_chart(df).to_dict()["mark"]["type"] == "bar"
    assert language_chart(share).to_dict()["encoding"]["y"]["stack"] == "normalize"
    assert language_chart(share, False).to_dict()["encoding"]["y"]["stack"] == "zero"
    assert versions_chart(versions).to_dict()["encoding"]["y"]["scale"]["domain"] == [1, 5]


def test_unknown_versions_are_not_plotted_as_releases():
    df = prepare(pd.concat([sample().iloc[[2]]] * 40, ignore_index=True).drop(columns="review_id"))
    _, _, versions = _cached_analysis_tables(df, "ME")
    assert versions.empty


def test_spike_details_include_reviews_late_on_the_final_period_day():
    df = prepare(pd.DataFrame([
        {"review_created_at": "2026-01-31T23:45:00Z", "score": 1, "lang": "vi", "app_version": "2.0", "content": "audio crash"},
        {"review_created_at": "2026-02-01T00:00:00Z", "score": 5, "lang": "en", "app_version": "3.0", "content": "all good"},
    ]))
    spikes = pd.DataFrame([{"period": pd.Timestamp("2026-01-31", tz="UTC"), "is_spike": True,
                            "n": 1, "baseline": .5, "avg_score": 1, "tone": "negative"}])
    for freq in ["D", "ME"]:
        detail = spike_details(df, spikes, freq)[0]
        assert detail["langs"] == {"vi": 1}
        assert detail["new_versions"] == ["2.0"]


def seed(db):
    init_db(db)
    save_app_name("com.example", "Example", db)
    save_app_name("com.pending", "Pending app", db)
    save_reviews([
        {"reviewId": "r1", "content": "Great", "score": 5, "at": "2026-01-01", "lang": "en"},
        {"reviewId": "r2", "content": "Slow", "score": 1, "at": "2026-01-02", "lang": "vi"},
    ], "com.example", db)


def test_library_summary_keeps_empty_apps_and_reconciles_reviews(tmp_path):
    db = str(tmp_path / "library.db")
    seed(db)
    summary = app_library_summary(db).set_index("package_id")
    assert summary.loc["com.example", "reviews"] == 2
    assert summary.loc["com.example", "average_rating"] == 3
    assert summary.loc["com.example", "languages"] == 2
    assert summary.loc["com.pending", "reviews"] == 0
    assert pd.isna(summary.loc["com.pending", "average_rating"])


def test_library_navigation_and_small_sample_analytics(tmp_path, monkeypatch):
    db = str(tmp_path / "ui.db")
    seed(db)
    monkeypatch.setenv("MERICRAWLER_DB_PATH", db)
    monkeypatch.setenv("MERICRAWLER_EMBED_WORKER", "0")
    at = AppTest.from_file(str(Path(__file__).parents[1] / "src/app.py"), default_timeout=15).run()
    at.radio(key="workspace_view").set_value("Apps").run()
    assert not at.exception
    at.text_input(key="library_search").set_value("Example").run()
    assert len(at.dataframe[0].value) == 1
    next(b for b in at.button if b.label == "Open insights").click().run()
    assert at.radio(key="workspace_view").value == "Insights"
    assert at.selectbox(key="result_picker").value == "com.example"
    assert len(at.get("vega_lite_chart") + at.get("arrow_vega_lite_chart")) == 0  # Reviews doesn't render hidden charts.
    at.radio(key="detail_view").set_value("Analytics").run()
    assert not at.exception
    assert any("Small sample" in notice.value for notice in at.info)
    assert at.metric[0].value == "2"
    assert len(at.get("vega_lite_chart") + at.get("arrow_vega_lite_chart")) == 3
    at.radio(key="analytics_view_com.example").set_value("Versions").run()
    assert not at.exception
    assert any("No known app version" in notice.value for notice in at.info)
    at.radio(key="analytics_view_com.example").set_value("Signals").run()
    assert not at.exception
    assert any("No volume spikes" in notice.value for notice in at.info)
