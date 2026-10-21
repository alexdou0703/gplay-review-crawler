import threading

from crawler import gplay_crawler as gc
from crawler.rate_limiter import RequestLimiter
from crawl_jobs import claim_job
from crawl_worker import run_job
from storage.sqlite_store import init_db, enqueue_job, get_job, count_reviews, retry_job


def test_worker_runs_claimed_job_and_persists_progress(monkeypatch, tmp_path):
    db = str(tmp_path / "worker.db")
    init_db(db)
    enqueue_job("com.x", db, langs=["en"], count_per_lang=2, delay=0)
    job = claim_job(db, "worker-a")

    def fake_fetch(package_id, lang, country, page_size, cursor, **kwargs):
        return ([{"reviewId": "r1", "content": "ok", "score": 5}], None)

    monkeypatch.setattr(gc, "_fetch_page", fake_fetch)
    run_job(job, db, "worker-a", RequestLimiter(min_interval=0), threading.Event())

    saved = get_job(job["job_id"], db)
    assert saved["status"] == "complete"
    assert saved["languages_completed"] == 1
    assert count_reviews("com.x", db) == 1


def test_job_stays_active_between_languages(monkeypatch, tmp_path):
    db = str(tmp_path / "worker.db")
    init_db(db)
    job_id = enqueue_job("com.x", db, langs=["en", "vi"], delay=0)
    job = claim_job(db, "worker-a")
    observed = []

    def fetch(package_id, lang, *args, **kwargs):
        observed.append(get_job(job_id, db)["status"])
        return ([{"reviewId": lang}], None)

    monkeypatch.setattr(gc, "_fetch_page", fetch)
    run_job(job, db, "worker-a", RequestLimiter(0), threading.Event())
    assert observed == ["running", "running"]
    assert get_job(job_id, db)["languages_completed"] == 2


def test_retry_skips_finished_languages_and_keeps_progress(monkeypatch, tmp_path):
    db = str(tmp_path / "worker.db")
    init_db(db)
    job_id = enqueue_job("com.x", db, langs=["en", "vi"], delay=0)
    monkeypatch.setattr(gc, "BACKOFF_DELAYS", [])

    def fetch(package_id, lang, *args, **kwargs):
        if lang == "vi":
            raise ConnectionError("temporary outage")
        return ([{"reviewId": lang}], None)

    monkeypatch.setattr(gc, "_fetch_page", fetch)
    run_job(claim_job(db, "worker-a"), db, "worker-a", RequestLimiter(0), threading.Event())
    assert get_job(job_id, db)["languages_completed"] == 1
    assert get_job(job_id, db)["status"] == "partial"
    assert retry_job(job_id, db)
    called = []

    def recovered(package_id, lang, *args, **kwargs):
        called.append(lang)
        return ([{"reviewId": lang}], None)

    monkeypatch.setattr(gc, "_fetch_page", recovered)
    run_job(claim_job(db, "worker-b"), db, "worker-b", RequestLimiter(0), threading.Event())
    assert called == ["vi"]
    saved = get_job(job_id, db)
    assert saved["status"] == "complete"
    assert saved["languages_completed"] == 2


def test_cancel_stops_before_next_language(monkeypatch, tmp_path):
    from crawl_service import crawl_package
    db = str(tmp_path / "worker.db")
    init_db(db)
    cancel = threading.Event()
    called = []

    def fetch(package_id, lang, *args, **kwargs):
        called.append(lang)
        return ([{"reviewId": lang}], None)

    monkeypatch.setattr(gc, "_fetch_page", fetch)
    crawl_package("com.x", db, ["en", "vi"], delay=0, cancel_event=cancel,
                  language_callback=lambda *a: cancel.set())
    assert called == ["en"]


def test_worker_restart_at_16_of_20_resumes_remaining_languages(monkeypatch, tmp_path):
    import sqlite3
    from crawl_service import crawl_package
    db = str(tmp_path / "worker.db")
    init_db(db)
    langs = [f"lang{i}" for i in range(20)]
    job_id = enqueue_job("com.x", db, langs=langs, delay=0)
    claim_job(db, "worker-a")
    cancel = threading.Event()

    def completed(lang, state):
        if lang == langs[15]:
            cancel.set()  # simulates shutdown after the 16th language checkpoint

    monkeypatch.setattr(gc, "_fetch_page", lambda pkg, lang, *a, **k: ([{"reviewId": lang}], None))
    crawl_package("com.x", db, langs, delay=0, job_id=job_id, job_worker_id="worker-a",
                  cancel_event=cancel, language_callback=completed)
    assert get_job(job_id, db)["languages_completed"] == 16
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE crawl_jobs SET lease_expires_at='2000-01-01'")
    called = []

    def fetch(pkg, lang, *a, **k):
        called.append(lang)
        return ([{"reviewId": lang}], None)

    monkeypatch.setattr(gc, "_fetch_page", fetch)
    run_job(claim_job(db, "worker-b"), db, "worker-b", RequestLimiter(0), threading.Event())
    assert called == langs[16:]
    assert get_job(job_id, db)["languages_completed"] == 20
    assert get_job(job_id, db)["status"] == "complete"
    assert count_reviews("com.x", db) == 20


def test_sync_uses_shared_limiter_and_saves_page_progress(monkeypatch, tmp_path):
    db = str(tmp_path / "worker.db")
    init_db(db)
    job_id = enqueue_job("com.x", db, langs=["en", "vi"], mode="sync", delay=0)
    limiter = RequestLimiter(0)
    observed = []

    def fetch(pkg, lang, *a, **kwargs):
        assert kwargs["limiter"] is limiter
        observed.append(get_job(job_id, db)["pages_completed"])
        return ([{"reviewId": lang}], None)

    monkeypatch.setattr(gc, "_fetch_page", fetch)
    run_job(claim_job(db, "worker-a"), db, "worker-a", limiter, threading.Event())
    job = get_job(job_id, db)
    assert observed == [0, 1]
    assert job["status"] == "complete"
    assert job["languages_completed"] == 2
    assert job["pages_completed"] == 2
    assert job["fetched_count"] == 2
