"""Streamlit integration tests use only isolated queues and disabled workers."""

from pathlib import Path
import csv
from io import StringIO
import json

import pytest
from streamlit.testing.v1 import AppTest

from storage.sqlite_store import (
    claim_job, enqueue_job, get_job, init_db, queue_snapshot, retry_job, save_app_name,
    save_reviews, set_job_status,
)


@pytest.fixture
def ui_db(tmp_path, monkeypatch):
    db = str(tmp_path / "ui.db")
    init_db(db)
    monkeypatch.setenv("MERICRAWLER_DB_PATH", db)
    monkeypatch.setenv("MERICRAWLER_EMBED_WORKER", "0")
    return db


def launch():
    at = AppTest.from_file(str(Path(__file__).parents[1] / "src" / "app.py"), default_timeout=15).run()
    assert not at.exception
    return at


def page_text(at):
    return "\n".join(element.value for element in at.markdown)


def test_wait_notices_persist_across_refresh_and_job_transitions(ui_db):
    ids = [enqueue_job(f"com.app{i}", ui_db, app_name=f"App {i}", langs=["en"])
           for i in range(5)]
    claim_job(ui_db, "a")
    claim_job(ui_db, "b")
    at = launch()
    for _ in range(2):
        assert page_text(at).count("Currently processing: App 0, App 1") == 1
        table = at.dataframe[0].value
        assert list(table.loc[table["Status"] == "Queued", "Queue #"]) == [1, 2, 3]
        at.run()
        assert not at.exception
    set_job_status(ids[0], ui_db, "complete")
    assert claim_job(ui_db, "a")["job_id"] == ids[2]
    at.run()
    assert not at.exception
    assert page_text(at).count("Currently processing: App 1, App 2") == 1
    table = at.dataframe[0].value
    assert list(table.loc[table["Status"] == "Queued", "Queue #"]) == [1, 2]


def test_open_reviews_navigates_to_saved_app_and_back(ui_db):
    save_app_name("com.example", "Example", ui_db)
    save_reviews([{"reviewId": "r1", "userName": "Alice", "content": "Useful app",
                   "score": 5, "thumbsUpCount": 0, "at": "2026-01-01", "lang": "en"}],
                 "com.example", ui_db)
    job_id = enqueue_job("com.example", ui_db, langs=["en"])
    at = launch()
    at.radio(key="workspace_view").set_value("Insights").run()
    assert not at.exception
    assert at.radio(key="workspace_view").value == "Insights"
    assert at.selectbox(key="result_picker").value == "com.example"
    assert any("active crawl" in notice.value for notice in at.info)
    assert any("Useful app" in frame.value.to_string() for frame in at.dataframe)
    at.radio(key="workspace_view").set_value("Crawl").run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0]["Package ID"] == "com.example"


def test_review_filters_and_exports_survive_workspace_navigation(ui_db, monkeypatch):
    import streamlit as st

    exports = {}
    original_download_button = st.download_button

    def record_download(label, data, **kwargs):
        exports[label] = data
        return original_download_button(label, data=data, **kwargs)

    monkeypatch.setattr(st, "download_button", record_download)
    save_app_name("com.filtered", "Filtered app", ui_db)
    save_reviews([
        {"reviewId": "positive", "content": "No crash now", "score": 5, "at": "2026-01-01"},
        {"reviewId": "negative", "content": "CRASH on launch", "score": 1, "at": "2026-01-02"},
        {"reviewId": "other", "content": "Slow to open", "score": 2, "at": "2026-01-03"},
    ], "com.filtered", ui_db)
    job_id = enqueue_job("com.filtered", ui_db, langs=["en"])
    at = launch()
    at.radio(key="workspace_view").set_value("Insights").run()
    at.text_input(key="review_search").set_value("crash").run()
    assert not at.exception
    at.checkbox(key="star_filter_5").uncheck().run()
    assert not at.exception

    def assert_filtered_results():
        assert at.text_input(key="review_search").value == "crash"
        assert not at.checkbox(key="star_filter_5").value
        table = next(frame.value for frame in at.dataframe if "Review" in frame.value.columns)
        assert list(table["Review"]) == ["CRASH on launch"]
        assert list(table["Rating"]) == [1]
        assert [row["review_id"] for row in csv.DictReader(StringIO(exports["Download CSV"]))] == ["negative"]
        assert [row["review_id"] for row in json.loads(exports["Download JSON"])] == ["negative"]

    assert_filtered_results()
    at.radio(key="workspace_view").set_value("Crawl").run()
    assert not at.exception
    at.radio(key="workspace_view").set_value("Insights").run()
    assert not at.exception
    assert_filtered_results()


def test_insights_warns_about_active_retry_of_older_attempt(ui_db):
    save_app_name("com.example", "Example", ui_db)
    save_reviews([{"reviewId": "r1", "content": "Saved result", "score": 3, "at": "2026-01-01"}],
                 "com.example", ui_db)
    older = enqueue_job("com.example", ui_db, langs=["en"])
    set_job_status(older, ui_db, "failed")
    newer = enqueue_job("com.example", ui_db, langs=["en"])
    set_job_status(newer, ui_db, "complete")
    assert retry_job(older, ui_db)
    assert claim_job(ui_db, "worker-a")["job_id"] == older
    at = launch()
    at.radio(key="workspace_view").set_value("Insights").run()
    assert not at.exception
    assert any("active crawl" in notice.value and "saved snapshot" in notice.value for notice in at.info)
    assert any("Saved result" in frame.value.to_string() for frame in at.dataframe)


def test_form_accepts_multiple_links_and_package_ids_without_metadata_network(ui_db, monkeypatch):
    import crawler.url_parser as parser

    def no_network(*args, **kwargs):
        pytest.fail("Package IDs and Play links must enqueue without metadata requests")

    monkeypatch.setattr(parser, "search", no_network)
    at = launch()
    submit = next(button for button in at.button if button.label == "Add to crawl queue")
    assert not submit.disabled
    at.text_area[0].set_value("com.first\nhttps://play.google.com/store/apps/details?id=com.second&gl=vn\ncom.third")
    next(select for select in at.selectbox if select.label == "Language").set_value("en")
    submit.click().run()
    assert not at.exception
    jobs = queue_snapshot(ui_db)["active"]
    assert [job["package_id"] for job in jobs] == ["com.first", "com.second", "com.third"]
    assert [job["country"] for job in jobs] == ["us", "vn", "us"]
    assert all(job["languages"] == ["en"] for job in jobs)
    assert page_text(at).count("Waiting for the crawl service") == 1


def test_empty_form_has_actionable_validation(ui_db):
    at = launch()
    next(button for button in at.button if button.label == "Add to crawl queue").click().run()
    assert not at.exception
    assert "Enter at least one Google Play URL or package ID" in page_text(at)
    assert not queue_snapshot(ui_db)["active"]


def test_queue_names_and_error_details_are_escaped(ui_db):
    job_id = enqueue_job("com.example", ui_db, app_name="<script>alert(1)</script>", langs=["en"])
    set_job_status(job_id, ui_db, "failed", error_msg="<script>bad</script>")
    at = launch()
    assert at.dataframe[0].value.iloc[0]["App"] == "<script>alert(1)</script>"
    assert "<script>alert(1)</script>" not in page_text(at)
    assert not at.expander or all(e.label != "Error details" for e in at.expander)


def test_table_saved_count_updates_after_first_saved_page(ui_db):
    job_id = enqueue_job("com.new", ui_db, langs=["en"])
    at = launch()
    assert at.dataframe[0].value.iloc[0]["Saved reviews"] == 0
    save_reviews([{"reviewId": "first", "content": "First saved page", "score": 4,
                   "at": "2026-01-01"}], "com.new", ui_db)
    at.run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0]["Saved reviews"] == 1
    at.radio(key="workspace_view").set_value("Insights").run()
    assert not at.exception
    assert at.radio(key="detail_view").value == "Reviews"
    assert any("First saved page" in frame.value.to_string() for frame in at.dataframe)


def test_preview_explains_disabled_crawling_without_repeated_worker_warnings(ui_db, monkeypatch):
    monkeypatch.setenv("MERICRAWLER_PREVIEW", "1")
    for package in ("demo.one", "demo.two"):
        enqueue_job(package, ui_db, langs=["en"])
    at = launch()
    assert "queue-guidance-info\" role=" not in page_text(at)
    assert any("live crawling is off" in caption.value for caption in at.caption)
    assert "Waiting for the crawl service" not in page_text(at)
    assert list(at.dataframe[0].value["Next step"]) == ["Preview only · live crawling is off"] * 2


def test_table_progress_refreshes_without_selection(ui_db):
    from storage.sqlite_store import update_job_progress
    job_id = enqueue_job("com.progress", ui_db, langs=["en", "vi"])
    claim_job(ui_db, "worker-a")
    at = launch()
    update_job_progress(job_id, ui_db, worker_id="worker-a", languages_completed=1)
    at.run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0]["Progress"] == 50
    assert not any(button.key and button.key.startswith(("open_", "cancel_", "retry_")) for button in at.button)
    assert not at.dataframe[0].proto.selection_mode
