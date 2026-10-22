"""Queue notices must describe actual scheduling state, including recovery."""

from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from queue_view import job_notice, queue_groups
from storage.sqlite_store import (
    claim_job, enqueue_job, get_job, init_db, latest_package_job,
    queue_snapshot, request_job_cancel, retry_job, set_job_status, update_job_progress,
)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "queue.db")
    init_db(path)
    return path


def add_jobs(db, count=5):
    return [enqueue_job(f"com.app{i}", db, app_name=f"App {i}", langs=["en"])
            for i in range(count)]


def groups(db):
    now = datetime.now(timezone.utc)
    return now, queue_groups(queue_snapshot(db)["active"], now)


def test_five_apps_two_processing_three_fifo_notices(db):
    ids = add_jobs(db)
    assert claim_job(db, "worker-a")["job_id"] == ids[0]
    assert claim_job(db, "worker-b")["job_id"] == ids[1]
    now, (processing, pending, positions) = groups(db)
    assert [job["job_id"] for job in processing] == ids[:2]
    assert positions == dict(zip(ids[2:], [1, 2, 3]))
    for position, job in enumerate(pending, 1):
        notice = job_notice(job, processing, positions, now)
        assert notice.label == f"Waiting for a slot · #{position}"
        assert "App 0, App 1" in notice.message
        assert "starts automatically" in notice.message
        assert "submit it again" in notice.message


def test_network_backoff_keeps_processing_slot_and_counts_down(db):
    ids = add_jobs(db, 2)
    claim_job(db, "worker-a")
    now = datetime.now(timezone.utc)
    update_job_progress(ids[0], db, worker_id="worker-a", status="waiting",
                        next_retry_at=(now + timedelta(seconds=8)).isoformat())
    processing, pending, positions = queue_groups(queue_snapshot(db)["active"], now)
    assert len(processing) == len(pending) == 1
    assert positions == {ids[1]: 1}
    notice = job_notice(processing[0], processing, positions, now)
    assert notice.label == "Retrying request"
    assert "Retrying in 8s" in notice.message
    assert "already processing" in notice.message
    assert "App 0" in job_notice(pending[0], processing, positions, now).message


@pytest.mark.parametrize("heartbeat", [None, "invalid", "2000-01-01T00:00:00+00:00"])
def test_stale_or_missing_heartbeat_does_not_claim_workers_are_busy(db, heartbeat):
    ids = add_jobs(db, 2)
    claim_job(db, "worker-a")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE crawl_jobs SET heartbeat_at=? WHERE job_id=?", (heartbeat, ids[0]))
    now, (processing, pending, positions) = groups(db)
    active_notice = job_notice(processing[0], processing, positions, now)
    assert active_notice.label == "Worker not responding"
    assert "previous claim expires" in active_notice.message
    queued_notice = job_notice(pending[0], processing, positions, now)
    assert queued_notice.label == "Waiting for a worker"
    assert "saved in the queue" in queued_notice.message
    assert "Currently processing" not in queued_notice.message


def test_empty_worker_pool_keeps_job_saved(db):
    add_jobs(db, 1)
    now, (processing, pending, positions) = groups(db)
    notice = job_notice(pending[0], processing, positions, now)
    assert notice.label == "Waiting for a worker"
    assert notice.tone == "warning"
    assert positions[pending[0]["job_id"]] == 1


def test_future_retry_excluded_until_eligible_and_actual_claim_agrees(db):
    ids = add_jobs(db, 3)
    now = datetime.now(timezone.utc)
    eligible_at = now + timedelta(minutes=5)
    set_job_status(ids[0], db, "retrying", next_retry_at=eligible_at.isoformat())
    active = queue_snapshot(db)["active"]
    processing, pending, positions = queue_groups(active, now)
    assert positions == {ids[1]: 1, ids[2]: 2}
    assert job_notice(pending[0], processing, positions, now).label == "Retry scheduled"
    assert queue_groups(active, eligible_at)[2] == dict(zip(ids, [1, 2, 3]))
    assert claim_job(db, "worker-a")["job_id"] == ids[1]


def test_cancel_and_claim_refresh_queue_positions(db):
    ids = add_jobs(db, 4)
    claim_job(db, "worker-a")
    request_job_cancel(ids[1], db)
    now, (processing, pending, positions) = groups(db)
    assert positions == {ids[2]: 1, ids[3]: 2}
    assert get_job(ids[1], db)["status"] == "cancelled"
    request_job_cancel(ids[0], db)
    now, (processing, pending, positions) = groups(db)
    assert job_notice(processing[0], processing, positions, now).label == "Cancelling"
    assert claim_job(db, "worker-b")["job_id"] == ids[2]
    assert groups(db)[1][2] == {ids[3]: 1}


def test_large_history_never_hides_active_jobs_and_latest_is_package_specific(db):
    active = add_jobs(db, 3)
    claim_job(db, "worker-a")
    for i in range(55):
        historical = enqueue_job(f"com.history{i}", db, langs=["en"])
        set_job_status(historical, db, "complete")
    snapshot = queue_snapshot(db)
    assert [job["job_id"] for job in snapshot["active"]] == active
    assert len(snapshot["history"]) == 20
    assert snapshot["history_count"] == 55
    assert latest_package_job("com.app0", db)["job_id"] == active[0]
    assert latest_package_job("com.missing", db) is None
    assert queue_snapshot(db, history_limit=0)["history"] == []


def test_retried_older_job_takes_priority_over_newer_completed_attempt(db):
    older = enqueue_job("com.example", db, langs=["en"])
    set_job_status(older, db, "failed")
    newer = enqueue_job("com.example", db, langs=["en"])
    set_job_status(newer, db, "complete")
    assert latest_package_job("com.example", db)["job_id"] == newer
    assert retry_job(older, db)
    assert latest_package_job("com.example", db)["job_id"] == older
    assert claim_job(db, "worker-a")["job_id"] == older
    latest = latest_package_job("com.example", db)
    assert (latest["job_id"], latest["status"]) == (older, "running")


@pytest.mark.parametrize("status,label,tone", [
    ("complete", "Complete", "success"),
    ("cancelled", "Cancelled", "info"),
    ("failed", "Failed", "error"),
    ("partial", "Partial results", "warning"),
    ("throttled", "Rate limited", "warning"),
])
def test_finished_status_notices_preserve_saved_results(db, status, label, tone):
    job_id = add_jobs(db, 1)[0]
    set_job_status(job_id, db, status)
    notice = job_notice(get_job(job_id, db), [], {}, datetime.now(timezone.utc))
    assert (notice.label, notice.tone) == (label, tone)
    assert "saved" in notice.message.lower()


def test_scheduled_retry_does_not_report_unavailable_service(db):
    from queue_view import queue_guidance
    job_id = add_jobs(db, 1)[0]
    now = datetime.now(timezone.utc)
    set_job_status(job_id, db, "retrying", next_retry_at=(now + timedelta(minutes=5)).isoformat())
    processing, pending, _ = queue_groups(queue_snapshot(db)["active"], now)
    assert queue_guidance(processing, pending, now) is None
    assert queue_guidance(processing, pending, now + timedelta(minutes=6)).tone == "warning"


def test_queue_guidance_does_not_claim_stale_processing_is_busy(db):
    from queue_view import queue_guidance
    ids = add_jobs(db, 2)
    claim_job(db, "worker-a")
    now, (processing, pending, _) = groups(db)
    assert "Currently processing: App 0" in queue_guidance(processing, pending, now).message
    guidance = queue_guidance(processing, pending, now + timedelta(seconds=30))
    assert guidance.tone == "warning"
    assert "Currently processing" not in guidance.message
