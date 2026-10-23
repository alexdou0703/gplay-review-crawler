"""Comparison navigation, submission and fresh-data behavior in Streamlit."""

from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from storage.sqlite_store import init_db, save_app_name, save_reviews, delete_package


def app(tmp_path, monkeypatch, count=3):
    db = str(tmp_path / "compare-ui.db")
    init_db(db)
    for i in range(count):
        pkg = f"com.app{i}"
        save_app_name(pkg, "Same name" if i < 2 else f"App {i}", db)
        save_reviews([
            {"reviewId": f"{pkg}-1", "content": "Useful", "score": 5,
             "at": "2026-01-01", "lang": "en"},
            {"reviewId": f"{pkg}-2", "content": "Slow", "score": i % 5 + 1,
             "at": "2026-01-08", "lang": "vi"},
        ], pkg, db)
    monkeypatch.setenv("MERICRAWLER_DB_PATH", db)
    monkeypatch.setenv("MERICRAWLER_EMBED_WORKER", "0")
    at = AppTest.from_file(str(Path(__file__).parents[1] / "src/app.py"), default_timeout=20).run()
    at.radio(key="workspace_view").set_value("Insights").run()
    at.radio(key="insights_mode").set_value("Compare apps").run()
    return at, db


def charts(at):
    return at.get("vega_lite_chart") + at.get("arrow_vega_lite_chart")


def submit(at):
    next(b for b in at.button if b.label == "Compare").click().run()
    return at


def summary(at):
    return next(frame.value for frame in at.dataframe if "Reviews in range" in frame.value.columns)


def test_comparison_requires_two_saved_apps(tmp_path, monkeypatch):
    at, _ = app(tmp_path, monkeypatch, 1)
    assert not at.exception
    assert any("at least two apps" in notice.value for notice in at.info)
    assert not charts(at)
    assert len(at.multiselect) == 0


def test_compare_duplicate_names_metric_switch_and_single_navigation(tmp_path, monkeypatch):
    at, _ = app(tmp_path, monkeypatch)
    assert not at.exception
    assert not charts(at)
    submit(at)
    assert not at.exception
    assert len(charts(at)) == 2
    table = summary(at)
    assert list(table["App"]) == ["Same name", "Same name"]
    assert set(table["Package ID"]) == {"com.app0", "com.app1"}
    colors = dict(at.session_state["compare_colors"])
    for metric in ["1–2 star share", "Saved review count", "Developer reply rate", "Average rating"]:
        at.selectbox(key="compare_metric").set_value(metric).run()
        assert not at.exception
        assert len(charts(at)) == 2
        assert dict(at.session_state["compare_colors"]) == colors
    at.radio(key="workspace_view").set_value("Apps").run()
    at.selectbox(key="library_picker").set_value("com.app1").run()
    next(b for b in at.button if b.label == "Open insights").click().run()
    assert not at.exception
    assert at.radio(key="insights_mode").value == "Single app"
    assert at.selectbox(key="result_picker").value == "com.app1"
    at.radio(key="detail_view").set_value("Analytics").run()
    assert not at.exception
    assert len(charts(at)) == 3
    at.radio(key="insights_mode").set_value("Compare apps").run()
    assert not at.exception
    assert len(charts(at)) == 2


def test_invalid_selection_and_partial_date_remove_old_charts(tmp_path, monkeypatch):
    at, _ = app(tmp_path, monkeypatch)
    submit(at)
    at.multiselect(key="compare_apps").set_value(["com.app0"])
    submit(at)
    assert not at.exception
    assert not charts(at)
    assert any("between 2 and 5" in notice.value for notice in at.warning)
    at.multiselect(key="compare_apps").set_value(["com.app0", "com.app1"])
    at.date_input(key="compare_dates").set_value((date(2026, 1, 1),))
    submit(at)
    assert not at.exception
    assert not charts(at)
    assert any("start and end date" in notice.value for notice in at.warning)


def test_empty_range_keeps_apps_and_null_rates(tmp_path, monkeypatch):
    at, _ = app(tmp_path, monkeypatch)
    at.date_input(key="compare_dates").set_value((date(2026, 2, 1), date(2026, 2, 28)))
    submit(at)
    assert not at.exception
    assert not charts(at)
    table = summary(at)
    assert table["Reviews in range"].tolist() == [0, 0]
    assert table["Average rating"].isna().all()
    assert table["Reply %"].isna().all()
    assert any("No rated, dated reviews" in notice.value for notice in at.info)


def test_refresh_keeps_filters_and_loads_new_rows(tmp_path, monkeypatch):
    at, db = app(tmp_path, monkeypatch)
    submit(at)
    dates = at.date_input(key="compare_dates").value
    selected = at.multiselect(key="compare_apps").value
    assert summary(at).set_index("Package ID").loc["com.app0", "Reviews in range"] == 2
    save_reviews([{"reviewId": "new", "content": "Excellent", "score": 5,
                   "at": "2026-01-08", "lang": "en"}], "com.app0", db)
    at.button(key="compare_refresh").click().run()
    assert not at.exception
    assert summary(at).set_index("Package ID").loc["com.app0", "Reviews in range"] == 3
    assert at.date_input(key="compare_dates").value == dates
    assert at.multiselect(key="compare_apps").value == selected


def test_deleted_selected_app_requires_new_comparison(tmp_path, monkeypatch):
    at, db = app(tmp_path, monkeypatch)
    submit(at)
    delete_package("com.app0", db)
    at.button(key="compare_refresh").click().run()
    assert not at.exception
    assert not charts(at)
    assert "com.app0" not in at.multiselect(key="compare_apps").value
    assert any("app was removed" in notice.value for notice in at.info)


def test_five_apps_and_period_limit(tmp_path, monkeypatch):
    at, _ = app(tmp_path, monkeypatch, 6)
    selected = [f"com.app{i}" for i in range(5)]
    at.multiselect(key="compare_apps").set_value(selected)
    submit(at)
    assert not at.exception
    assert len(summary(at)) == 5
    colors = at.session_state["compare_colors"]
    assert len({colors[p] for p in selected}) == 5
    at.date_input(key="compare_dates").set_value((date(2020, 1, 1), date(2026, 1, 8)))
    at.selectbox(key="compare_frequency").set_value("Daily")
    submit(at)
    assert not at.exception
    assert not charts(at)
    assert any("500 periods" in notice.value for notice in at.warning)


def test_applied_filters_survive_leaving_comparison(tmp_path, monkeypatch):
    at, _ = app(tmp_path, monkeypatch)
    selected = ["com.app1", "com.app2"]
    dates = (date(2026, 1, 1), date(2026, 1, 8))
    at.multiselect(key="compare_apps").set_value(selected)
    at.date_input(key="compare_dates").set_value(dates)
    at.selectbox(key="compare_frequency").set_value("Daily")
    submit(at)
    at.radio(key="insights_mode").set_value("Single app").run()
    at.radio(key="insights_mode").set_value("Compare apps").run()
    assert not at.exception
    assert at.multiselect(key="compare_apps").value == selected
    assert at.date_input(key="compare_dates").value == dates
    assert at.selectbox(key="compare_frequency").value == "Daily"
