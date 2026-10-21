---
phase: 2
title: "Durable multi-app job system"
status: in_progress
priority: P0
dependencies: [phase-01]
---

# Phase 2: Durable multi-app job system

## Overview

Move crawling out of the Streamlit script run. The browser becomes a control and monitoring surface that can enqueue many apps in one session while a worker process performs the network work and checkpoints every page.

## Requirements

- Functional: accept one app per line or multiple app entries in a batch; show each job independently; cancel and retry a job; open results while other jobs run.
- Non-functional: survive Streamlit reruns and worker restarts; prevent two active jobs from mutating the same package/language/country checkpoint.
- Operational: support a local command such as `python src/crawl_worker.py --db data/reviews.db --workers 2`.

## Architecture

Add a `crawl_jobs` table with a generated job ID, package/app metadata, country, language selection, mode, cap, status, progress counters, error fields, timestamps, worker ID, heartbeat, and cancellation request. Use an atomic SQLite claim transaction with a lease. A partial unique constraint or equivalent claim check must prevent duplicate active jobs for the same package/country target. Keep the existing `crawl_state` as the page-level resume checkpoint, and commit review rows plus checkpoint plus job progress in one transaction.

Create a worker entry point that owns the thread pool. Worker threads must call crawler/storage code only; they must never call `st.*` or mutate `st.session_state`. Default to two app workers and keep each app's language sweep sequential until Phase 3 measurements justify otherwise.

The Streamlit UI should replace the blocking crawl action with:

1. A multi-line queue form with shared language/cap/mode options.
2. A queue panel showing status, progress, last update, retry reason, and cancel/retry actions.
3. A selected-app view that reads fresh data from SQLite instead of retaining a stale DataFrame snapshot.
4. Polling through native supported Streamlit fragments where available, with a controlled refresh fallback for older versions.

## Related Code Files

- Modify: `src/storage/sqlite_store.py`
- Create: `src/crawl_jobs.py`
- Create: `src/crawl_worker.py`
- Modify: `src/crawl_service.py`
- Modify: `src/app.py`
- Modify: `README.md`
- Create: `tests/test_crawl_jobs.py`
- Create: `tests/test_crawl_worker.py`
- Modify: `tests/test_sqlite_store.py`

## Implementation Steps

1. Add idempotent schema migration for `crawl_jobs` and indexes for active jobs, status, and updated time.
2. Implement enqueue, claim, heartbeat, progress update, cancel request, retry, and lease recovery APIs.
3. Refactor the existing crawl service so callbacks update a job record while preserving page-level transactions.
4. Implement the worker process and clean shutdown behavior.
5. Replace the single blocking form with a multi-app queue and live job panel.
6. Update the CLI to enqueue or run directly with the same service primitives, preserving current flags and exit codes.

## Success Criteria

- [x] Five apps can be queued from one tab and appear as five independent jobs.
- [ ] The tab remains interactive while jobs are running and can display an already-finished app.
- [ ] Cancelling a job leaves saved pages intact and marks the job resumable/cancelled without reporting success.
- [ ] Killing the worker after a page commit and restarting it resumes from the stored cursor.
- [x] Two jobs for the same package/country cannot run concurrently against the same checkpoint.

## Risk Assessment

SQLite is suitable for a local single-host queue, not a multi-host distributed scheduler. Document that boundary. A thread pool is acceptable for network I/O, but the worker must use short-lived SQLite connections and busy timeouts to avoid sharing connections across threads.
