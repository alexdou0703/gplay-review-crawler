"""Saved-app management remains reachable without a sidebar."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from storage.sqlite_store import (
    app_library_summary, count_reviews, enqueue_job, init_db, latest_package_job,
    list_jobs, list_packages_with_names, save_app_name, save_reviews,
)


def library_app(tmp_path, monkeypatch, count=2):
    db = str(tmp_path / "library-management.db")
    init_db(db)
    for i in range(count):
        pkg = f"com.app{i}"
        save_app_name(pkg, f"App {i}", db)
        save_reviews([{"reviewId": f"review-{i}", "score": 5, "content": "Useful",
                       "at": "2026-01-01", "lang": "en"}], pkg, db)
    monkeypatch.setenv("MERICRAWLER_DB_PATH", db)
    monkeypatch.setenv("MERICRAWLER_EMBED_WORKER", "0")
    at = AppTest.from_file(str(Path(__file__).parents[1] / "src/app.py"), default_timeout=20).run()
    at.radio(key="workspace_view").set_value("Apps").run()
    return at, db


def test_no_sidebar_and_library_opens_selected_app(tmp_path, monkeypatch):
    at, _ = library_app(tmp_path, monkeypatch)
    assert not at.exception
    assert not at.sidebar.button
    assert not at.sidebar.title
    at.selectbox(key="library_picker").set_value("com.app1").run()
    next(b for b in at.button if b.label == "Open insights").click().run()
    assert not at.exception
    assert at.radio(key="workspace_view").value == "Insights"
    assert at.radio(key="insights_mode").value == "Single app"
    assert at.selectbox(key="result_picker").value == "com.app1"
    assert not at.sidebar.button


def test_sync_selected_app_enqueues_without_fetching_or_deleting(tmp_path, monkeypatch):
    at, db = library_app(tmp_path, monkeypatch)
    at.selectbox(key="library_picker").set_value("com.app1").run()
    at.button(key="library_sync").click().run()
    assert not at.exception
    assert at.radio(key="workspace_view").value == "Crawl"
    job = latest_package_job("com.app1", db)
    assert job["mode"] == "sync"
    assert job["status"] == "queued"
    assert job["languages"] == ["en"]
    assert latest_package_job("com.app0", db) is None
    assert count_reviews("com.app1", db) == 1


def test_delete_requires_confirmation_and_cancel_keeps_data(tmp_path, monkeypatch):
    at, db = library_app(tmp_path, monkeypatch)
    at.button(key="library_delete").click().run()
    assert not at.exception
    assert count_reviews("com.app0", db) == 1
    assert any("cannot be undone" in notice.value for notice in at.warning)
    at.button(key="library_delete_cancel").click().run()
    assert not at.exception
    assert count_reviews("com.app0", db) == 1
    assert not any(b.key == "library_delete_confirm" for b in at.button)


def test_confirm_deletes_only_selected_app_and_sanitizes_selection(tmp_path, monkeypatch):
    at, db = library_app(tmp_path, monkeypatch)
    at.selectbox(key="library_picker").set_value("com.app1").run()
    at.button(key="library_delete").click().run()
    at.button(key="library_delete_confirm").click().run()
    assert not at.exception
    assert count_reviews("com.app1", db) == 0
    assert count_reviews("com.app0", db) == 1
    assert list_packages_with_names(db) == [("com.app0", "App 0")]
    assert at.selectbox(key="library_picker").value == "com.app0"
    assert not any(b.key == "library_delete_confirm" for b in at.button)


def test_switching_app_dismisses_pending_delete(tmp_path, monkeypatch):
    at, db = library_app(tmp_path, monkeypatch)
    at.button(key="library_delete").click().run()
    at.selectbox(key="library_picker").set_value("com.app1").run()
    assert not at.exception
    assert not any(b.key == "library_delete_confirm" for b in at.button)
    assert count_reviews("com.app0", db) == 1
    assert count_reviews("com.app1", db) == 1


def test_deleting_final_app_leaves_usable_empty_state(tmp_path, monkeypatch):
    at, db = library_app(tmp_path, monkeypatch, count=1)
    next(b for b in at.button if b.label == "Open insights").click().run()
    at.radio(key="workspace_view").set_value("Apps").run()
    at.button(key="library_delete").click().run()
    at.button(key="library_delete_confirm").click().run()
    assert not at.exception
    assert list_packages_with_names(db) == []
    assert any("library is empty" in notice.value for notice in at.info)
    at.radio(key="workspace_view").set_value("Insights").run()
    assert not at.exception
    assert not any(select.key == "result_picker" for select in at.selectbox)
    assert any("first app in Crawl" in notice.value for notice in at.info)


def test_search_filters_sanitize_picker_and_empty_results(tmp_path, monkeypatch):
    at, _ = library_app(tmp_path, monkeypatch)
    at.selectbox(key="library_picker").set_value("com.app1").run()
    at.text_input(key="library_search").set_value("App 0").run()
    assert not at.exception
    assert at.selectbox(key="library_picker").value == "com.app0"
    assert len(at.dataframe[0].value) == 1
    at.text_input(key="library_search").set_value("missing-app").run()
    assert not at.exception
    assert any("No apps match" in notice.value for notice in at.info)
    assert not any(b.key in {"library_sync", "library_delete"} for b in at.button)
    at.text_input(key="library_search").set_value("").run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 2


def test_pending_app_cannot_sync_or_delete_initial_crawl(tmp_path, monkeypatch):
    at, db = library_app(tmp_path, monkeypatch, count=0)
    pkg = "com.pending"
    save_app_name(pkg, "Pending app", db)
    job_id = enqueue_job(pkg, db, app_name="Pending app", langs=["vi"],
                         country="vn", mode="crawl")
    at.run()
    assert not at.exception
    assert at.selectbox(key="library_picker").value == pkg
    assert at.button(key="library_sync").disabled
    assert at.button(key="library_delete").disabled
    assert not any(b.key == "library_delete_confirm" for b in at.button)
    next(b for b in at.button if b.label == "Open insights").click().run()
    assert not at.exception
    assert any("No saved reviews" in notice.value for notice in at.info)
    at.radio(key="workspace_view").set_value("Apps").run()
    assert not at.exception
    assert at.button(key="library_sync").disabled
    assert at.button(key="library_delete").disabled
    jobs = list_jobs(db)
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == job_id
    assert jobs[0]["country"] == "vn"
    assert jobs[0]["languages"] == ["vi"]
    assert jobs[0]["mode"] == "crawl"
    assert jobs[0]["status"] == "queued"
    summary = app_library_summary(db).set_index("package_id")
    assert summary.loc[pkg, "app_name"] == "Pending app"
    assert summary.loc[pkg, "reviews"] == 0
