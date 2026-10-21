import sqlite3
from datetime import datetime, timedelta, timezone

from crawl_jobs import display_status
from storage.sqlite_store import (
    init_db, enqueue_job, get_job, claim_job, heartbeat_job,
    request_job_cancel, retry_job, set_job_status, update_job_progress,
)


def test_queue_is_idempotent_for_active_package(tmp_path):
    db = str(tmp_path / "jobs.db")
    init_db(db)
    first = enqueue_job("com.x", db, langs=["en"], app_name="X")
    second = enqueue_job("com.x", db, langs=["vi"], app_name="X")
    assert first == second
    assert get_job(first, db)["languages"] == ["en"]


def test_claim_heartbeat_cancel_and_retry(tmp_path):
    db = str(tmp_path / "jobs.db")
    init_db(db)
    job_id = enqueue_job("com.x", db, langs=["en"])
    claimed = claim_job(db, "worker-a", lease_seconds=30)
    assert claimed["job_id"] == job_id
    assert claimed["status"] == "running"
    assert heartbeat_job(job_id, db, "worker-a")
    assert request_job_cancel(job_id, db)
    assert get_job(job_id, db)["cancel_requested"]
    set_job_status(job_id, db, "cancelled", event="cancelled")
    assert retry_job(job_id, db)
    assert get_job(job_id, db)["status"] == "queued"
    assert display_status("throttled") == "Rate limited"

    set_job_status(job_id, db, "throttled", error_msg="HTTP 429")
    assert get_job(job_id, db)["next_retry_at"]


def test_expired_lease_is_reclaimable(tmp_path):
    db = str(tmp_path / "jobs.db")
    init_db(db)
    job_id = enqueue_job("com.x", db, langs=["en"])
    claimed = claim_job(db, "worker-a", lease_seconds=1)
    expired = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE crawl_jobs SET lease_expires_at=? WHERE job_id=?", (expired, job_id))
    recovered = claim_job(db, "worker-b", lease_seconds=30)
    assert recovered["job_id"] == claimed["job_id"]
    assert recovered["worker_id"] == "worker-b"


def test_waiting_job_keeps_lease_and_recovers_after_restart(tmp_path):
    db = str(tmp_path / "jobs.db")
    init_db(db)
    job_id = enqueue_job("com.x", db, langs=["en"])
    claim_job(db, "worker-a")
    update_job_progress(job_id, db, worker_id="worker-a", status="waiting")
    assert heartbeat_job(job_id, db, "worker-a")
    expired = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE crawl_jobs SET lease_expires_at=?", (expired,))
    recovered = claim_job(db, "worker-b")
    assert recovered["job_id"] == job_id


def test_stale_worker_cannot_overwrite_recovered_job(tmp_path):
    from crawler.gplay_crawler import CrawlState
    from storage.sqlite_store import save_reviews_and_state, count_reviews
    import pytest
    db = str(tmp_path / "jobs.db")
    init_db(db)
    job_id = enqueue_job("com.x", db, langs=["en"])
    claim_job(db, "worker-a")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE crawl_jobs SET lease_expires_at='2000-01-01'")
    claim_job(db, "worker-b")
    state = CrawlState("com.x", "en", "us")
    with pytest.raises(InterruptedError):
        save_reviews_and_state([{"reviewId": "late"}], "com.x", state, db,
                               job_id=job_id, worker_id="worker-a")
    set_job_status(job_id, db, "failed", worker_id="worker-a")
    assert get_job(job_id, db)["status"] == "running"
    assert count_reviews("com.x", db) == 0


def test_retry_old_job_while_new_job_active_returns_false(tmp_path):
    db = str(tmp_path / "jobs.db")
    init_db(db)
    old = enqueue_job("com.x", db, langs=["en"])
    set_job_status(old, db, "failed")
    enqueue_job("com.x", db, langs=["en"])
    assert not retry_job(old, db)


def test_recovers_legacy_job_marked_complete_between_languages(tmp_path):
    from crawler.gplay_crawler import CrawlState
    from storage.sqlite_store import save_crawl_state, completed_job_languages
    db = str(tmp_path / "jobs.db")
    init_db(db)
    job_id = enqueue_job("com.x", db, langs=["en", "vi"])
    claim_job(db, "old-worker")
    state = CrawlState("com.x", "en", "us")
    state.status = "complete"
    save_crawl_state(state, db)
    update_job_progress(job_id, db, status="complete", languages_completed=1)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE crawl_jobs SET lease_expires_at='2000-01-01'")
    recovered = claim_job(db, "new-worker")
    assert recovered["job_id"] == job_id
    assert recovered["status"] == "running"
    assert recovered["languages_completed"] == 1
    assert completed_job_languages(job_id, db) == {"en"}
