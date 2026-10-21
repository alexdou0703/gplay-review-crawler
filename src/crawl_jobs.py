"""Application-facing durable queue API.

The storage module owns SQLite transactions; this module keeps job semantics
and display labels in one small place so Streamlit and the worker agree.
"""

from storage.sqlite_store import (
    enqueue_job, get_job, list_jobs, claim_job, heartbeat_job,
    update_job_progress, set_job_status, request_job_cancel, retry_job,
    is_job_cancel_requested,
)

JOB_LABELS = {
    "queued": "Queued",
    "running": "Running",
    "waiting": "Waiting",
    "retrying": "Retrying",
    "throttled": "Rate limited",
    "partial": "Partial",
    "complete": "Complete",
    "failed": "Failed",
    "cancelled": "Cancelled",
}


def display_status(status: str) -> str:
    return JOB_LABELS.get(status, status.replace("_", " ").title())


__all__ = [
    "enqueue_job", "get_job", "list_jobs", "claim_job", "heartbeat_job",
    "update_job_progress", "set_job_status", "request_job_cancel", "retry_job",
    "is_job_cancel_requested", "display_status", "JOB_LABELS",
]
