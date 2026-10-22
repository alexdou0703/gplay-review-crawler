"""Read-only queue presentation; worker scheduling stays in the storage layer."""

from dataclasses import dataclass
from datetime import datetime, timezone
import math

PROCESSING = {"running", "waiting"}
PENDING = {"queued", "retrying"}
HEARTBEAT_WARNING_SECONDS = 15


def timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def responsive(job, now):
    heartbeat = timestamp(job.get("heartbeat_at"))
    return heartbeat is not None and (now - heartbeat).total_seconds() <= HEARTBEAT_WARNING_SECONDS


def ready_to_start(job, now):
    scheduled = timestamp(job.get("next_retry_at"))
    return not job.get("cancel_requested") and (scheduled is None or scheduled <= now)


def queue_groups(active, now):
    ordered = sorted(active, key=lambda job: (job["created_at"], job["job_id"]))
    processing = [job for job in ordered if job["status"] in PROCESSING]
    pending = [job for job in ordered if job["status"] in PENDING]
    ready = [job for job in pending if ready_to_start(job, now)]
    return processing, pending, {job["job_id"]: i + 1 for i, job in enumerate(ready)}


@dataclass(frozen=True)
class QueueNotice:
    label: str
    message: str
    tone: str = "info"


def queue_guidance(processing, pending, now, *, preview_mode=False):
    """One shared explanation, without inferring service health from an idle queue."""
    if preview_mode:
        return QueueNotice("Preview mode · live crawling is off",
                           "You can add apps to the sample queue and view sample reviews. "
                           "Queued apps will not fetch new reviews in this preview.")
    if not any(ready_to_start(job, now) for job in pending):
        return None
    live = [job for job in processing if responsive(job, now)]
    if live:
        names = ", ".join(job.get("app_name") or job["package_id"] for job in live[:3])
        if len(live) > 3:
            names += f" and {len(live) - 3} more"
        return QueueNotice("Your apps are queued · no action needed",
                           f"Currently processing: {names}. Waiting apps start automatically as slots open.")
    return QueueNotice("Waiting for the crawl service",
                       "No active crawl worker has reported recently. Your apps are saved in the queue. "
                       "Do not add them again. If this persists, ask the service operator to check the worker.", "warning")


def job_notice(job, processing, positions, now):
    """Explain observable state without guessing worker capacity or an ETA."""
    status = job["status"]
    if job.get("cancel_requested") and status in PROCESSING | PENDING:
        return QueueNotice("Cancelling", "Cancellation requested. Saved reviews are kept.")
    if status in PENDING:
        scheduled = timestamp(job.get("next_retry_at"))
        if scheduled and scheduled > now:
            return QueueNotice("Retry scheduled", f"Eligible to retry at {scheduled:%H:%M:%S %Z}; then this app waits for a crawl slot.")
        position = positions.get(job["job_id"])
        label = f"Waiting for a slot · #{position}" if position else "Waiting for a slot"
        live = [item for item in processing if responsive(item, now)]
        if live:
            names = [item.get("app_name") or item["package_id"] for item in live[:3]]
            names_text = ", ".join(names)
            if len(live) > 3:
                names_text += f" and {len(live) - 3} more"
            return QueueNotice(label, f"Waiting for a crawl slot. Currently processing: {names_text}. "
                               "This app starts automatically when a slot opens; you do not need to submit it again.")
        return QueueNotice("Waiting for a worker", "No recently responding crawl worker is visible. "
                           "This app is saved in the queue and starts automatically when a worker is available.", "warning")
    if status in PROCESSING and not responsive(job, now):
        return QueueNotice("Worker not responding", "The worker has not reported recently. Saved reviews are kept; "
                           "this job can resume when a worker is available and its previous claim expires.", "warning")
    if status == "waiting":
        retry_at = timestamp(job.get("next_retry_at"))
        seconds = max(0, math.ceil((retry_at - now).total_seconds())) if retry_at else 0
        timing = f"Retrying in {seconds}s." if seconds else "Preparing the next request."
        return QueueNotice("Retrying request", f"{timing} This app is already processing; saved pages are kept.", "warning")
    if status == "running":
        return QueueNotice("Running", "Fetching reviews. Pages are saved as they arrive.")
    if status == "complete":
        return QueueNotice("Complete", "Finished the requested crawl. Open reviews to explore the saved results.", "success")
    if status == "cancelled":
        return QueueNotice("Cancelled", "Crawl cancelled. Saved reviews remain available; Retry continues unfinished languages.")
    if status in {"partial", "throttled", "failed"}:
        label = {"partial": "Partial results", "throttled": "Rate limited", "failed": "Failed"}[status]
        return QueueNotice(label, "Saved reviews remain available. Retry continues unfinished languages.",
                           "error" if status == "failed" else "warning")
    return QueueNotice(status.replace("_", " ").title(), "Review the job details below.")
