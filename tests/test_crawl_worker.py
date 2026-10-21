import threading

from crawler import gplay_crawler as gc
from crawler.rate_limiter import RequestLimiter
from crawl_jobs import claim_job
from crawl_worker import run_job
from storage.sqlite_store import init_db, enqueue_job, get_job, count_reviews


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
