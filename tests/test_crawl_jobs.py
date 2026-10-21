import sqlite3
from datetime import datetime, timedelta, timezone

from crawl_jobs import display_status
from storage.sqlite_store import (
    init_db, enqueue_job, get_job, claim_job, heartbeat_job,
    request_job_cancel, retry_job, set_job_status,
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
