"""Durable local worker for queued Mericrawler jobs."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
from concurrent.futures import ThreadPoolExecutor

from crawler.gplay_crawler import ALL_LANGUAGES
from crawler.rate_limiter import RequestLimiter
from crawl_jobs import (
    claim_job, heartbeat_job, is_job_cancel_requested, set_job_status,
    update_job_progress,
)
from crawl_service import crawl_package
from storage.sqlite_store import init_db

logger = logging.getLogger("mericrawler.worker")


def run_job(job: dict, db_path: str, worker_id: str, limiter: RequestLimiter,
            stop_event: threading.Event) -> None:
    job_id = job["job_id"]
    cancelled = threading.Event()

    def watch_cancel() -> None:
        while not stop_event.is_set() and not cancelled.is_set():
            if is_job_cancel_requested(job_id, db_path):
                cancelled.set()
                return
            heartbeat_job(job_id, db_path, worker_id)
            stop_event.wait(2.0)
        if stop_event.is_set():
            cancelled.set()

    watcher = threading.Thread(target=watch_cancel, daemon=True)
    watcher.start()
    try:
        langs = job["languages"] or ALL_LANGUAGES
        count = job["count_per_lang"]
        if job.get("mode") == "sync":
            # Queue jobs intentionally use the same package service surface;
            # direct sync remains available in the legacy CLI.
            from crawl_service import sync_package
            results = sync_package(
                job["package_id"], db_path, langs=langs, country=job["country"],
                delay=job["delay"], max_pages=25,
                cancel_event=cancelled,
                progress_callback=lambda lang, new, state: update_job_progress(
                    job_id, db_path, worker_id=worker_id, lang=lang,
                    fetched=state.fetched, inserted=new, languages_completed=1,
                    event=state.status,
                ),
            )
            if cancelled.is_set():
                set_job_status(job_id, db_path, "cancelled", event="cancelled")
                return
            statuses = [state.status for _, state in results.values()]
            final = "throttled" if "throttled" in statuses else "partial" if "partial" in statuses else "complete"
            set_job_status(job_id, db_path, final, event=final)
            return

        def language_callback(lang, state):
            update_job_progress(
                job_id, db_path, worker_id=worker_id, lang=lang,
                languages_completed=1, event=state.status,
                status="running" if state.status == "in_progress" else state.status,
                error_class="throttled" if state.status == "throttled" else None,
                error_msg=state.error_msg,
            )

        states = crawl_package(
            job["package_id"], db_path, langs, country=job["country"], count=count,
            delay=job["delay"], job_id=job_id, job_worker_id=worker_id,
            limiter=limiter, cancel_event=cancelled,
            request_callback=lambda event: update_job_progress(
                job_id, db_path, worker_id=worker_id,
                event=event["outcome"], status="waiting" if event["retry_delay"] else "running",
            ), language_callback=language_callback,
        )
        if cancelled.is_set() or any(s.status == "cancelled" for s in states.values()):
            set_job_status(job_id, db_path, "cancelled", event="cancelled")
        elif any(s.status == "throttled" for s in states.values()):
            set_job_status(job_id, db_path, "throttled", event="rate_limited")
        elif any(s.status == "error" for s in states.values()):
            set_job_status(job_id, db_path, "failed", event="failed")
        else:
            set_job_status(job_id, db_path, "complete", event="complete")
    except Exception as exc:
        logger.exception("job %s failed", job_id)
        set_job_status(job_id, db_path, "failed", error_class=type(exc).__name__,
                       error_msg=str(exc), event="failed")
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
            futures = {f for f in futures if not f.done()}
            while len(futures) < max(1, workers):
                slot_id = f"{worker_id}-{len(futures)}"
                job = claim_job(db_path, slot_id)
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
