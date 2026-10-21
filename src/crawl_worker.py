"""Durable local worker for queued Mericrawler jobs."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from crawler.gplay_crawler import ALL_LANGUAGES, fetch_app_name
from crawler.rate_limiter import RequestLimiter
from crawl_jobs import (
    claim_job, heartbeat_job, is_job_cancel_requested, set_job_status,
    update_job_progress,
)
from crawl_service import crawl_package
from storage.sqlite_store import init_db, save_app_name

logger = logging.getLogger("mericrawler.worker")


def run_job(job: dict, db_path: str, worker_id: str, limiter: RequestLimiter,
            stop_event: threading.Event) -> None:
    job_id = job["job_id"]
    cancelled = threading.Event()

    def watch_cancel() -> None:
        while not stop_event.is_set() and not cancelled.is_set():
            try:
                if is_job_cancel_requested(job_id, db_path) or not heartbeat_job(job_id, db_path, worker_id):
                    cancelled.set()
                    return
            except sqlite3.OperationalError:
                logger.warning("Heartbeat temporarily unavailable for %s", job_id, exc_info=True)
            cancelled.wait(0.5)
        if stop_event.is_set():
            cancelled.set()

    watcher = threading.Thread(target=watch_cancel, daemon=True)
    watcher.start()

    def finish(status, **kwargs):
        set_job_status(job_id, db_path, status, worker_id=worker_id, **kwargs)

    def request_callback(event):
        waiting = event["phase"] == "waiting"
        retry_at = (datetime.now(timezone.utc) + timedelta(seconds=event["retry_delay"])).isoformat() if waiting else None
        update_job_progress(
            job_id, db_path, worker_id=worker_id, lang=event["lang"],
            event=f"{event['outcome']} · attempt {event['attempt']}",
            status="waiting" if waiting else "running", next_retry_at=retry_at,
        )

    try:
        if job.get("app_name") == job["package_id"]:
            update_job_progress(job_id, db_path, worker_id=worker_id, event="loading app name")
            try:
                title = fetch_app_name(job["package_id"], country=job["country"])
                save_app_name(job["package_id"], title, db_path)
            except ValueError:
                raise
            except Exception:
                logger.warning("App title unavailable for %s; continuing with package ID", job["package_id"])
        langs = job["languages"] or ALL_LANGUAGES
        count = job["count_per_lang"]
        if job.get("mode") == "sync":
            # Queue jobs intentionally use the same package service surface;
            # direct sync remains available in the legacy CLI.
            from crawl_service import sync_package
            results = sync_package(
                job["package_id"], db_path, langs=langs, country=job["country"],
                delay=job["delay"], max_pages=25,
                cancel_event=cancelled, limiter=limiter, request_callback=request_callback,
                job_id=job_id, job_worker_id=worker_id,
            )
            if cancelled.is_set():
                finish("cancelled", event="cancelled")
                return
            statuses = [state.status for _, state in results.values()]
            final = "failed" if "error" in statuses else "throttled" if "throttled" in statuses else "partial" if "partial" in statuses else "complete"
            errors = [f"{lang}: {state.error_msg}" for lang, (_, state) in results.items() if state.error_msg]
            finish(final, event=final, error_msg="; ".join(errors) or None)
            return

        def language_callback(lang, state):
            update_job_progress(
                job_id, db_path, worker_id=worker_id, lang=lang,
                event=state.status, status="running",
                error_class="throttled" if state.status == "throttled" else None,
                error_msg=state.error_msg,
            )

        states = crawl_package(
            job["package_id"], db_path, langs, country=job["country"], count=count,
            delay=job["delay"], job_id=job_id, job_worker_id=worker_id,
            limiter=limiter, cancel_event=cancelled,
            request_callback=request_callback, language_callback=language_callback,
        )
        errors = "; ".join(f"{lang}: {s.error_msg}" for lang, s in states.items() if s.error_msg) or None
        if cancelled.is_set() or any(s.status == "cancelled" for s in states.values()):
            finish("cancelled", event="cancelled", error_msg=errors)
        elif any(s.status == "error" for s in states.values()):
            finish("failed", event="failed", error_msg=errors)
        elif any(s.status == "throttled" for s in states.values()):
            finish("throttled", event="retry_needed", error_msg=errors)
        elif any(s.status == "partial" for s in states.values()):
            finish("partial", event="retry_needed", error_msg=errors)
        else:
            finish("complete", event="complete")
    except Exception as exc:
        logger.exception("job %s failed", job_id)
        finish("failed", error_class=type(exc).__name__, error_msg=str(exc), event="failed")
    finally:
        cancelled.set()
        watcher.join(timeout=1)


def run_worker(db_path: str, workers: int = 2, min_request_interval: float = 1.0,
               poll_interval: float = 1.0, *, stop_event=None,
               install_signal_handlers: bool = True) -> None:
    init_db(db_path)
    stop_event = stop_event or threading.Event()
    worker_id = f"worker-{os.getpid()}"
    limiter = RequestLimiter(min_interval=min_request_interval)

    def stop(*_):
        stop_event.set()

    if install_signal_handlers:
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="crawl") as pool:
        futures = set()
        while not stop_event.is_set():
            for future in list(futures):
                if future.done():
                    futures.remove(future)
                    try:
                        future.result()
                    except Exception:
                        logger.exception("Worker task failed; its expired lease can be recovered")
            while len(futures) < max(1, workers):
                slot_id = f"{worker_id}-{uuid.uuid4().hex[:12]}"
                try:
                    job = claim_job(db_path, slot_id)
                except sqlite3.OperationalError:
                    logger.warning("Queue temporarily unavailable; retrying next poll", exc_info=True)
                    break
                if not job:
                    break
                futures.add(pool.submit(run_job, job, db_path, job["worker_id"], limiter, stop_event))
            stop_event.wait(poll_interval)
        for future in futures:
            future.result()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Mericrawler SQLite crawl worker")
    parser.add_argument("--db", default="data/reviews.db")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--min-request-interval", type=float, default=1.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    return parser


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args()
    run_worker(args.db, args.workers, args.min_request_interval, args.poll_interval)
