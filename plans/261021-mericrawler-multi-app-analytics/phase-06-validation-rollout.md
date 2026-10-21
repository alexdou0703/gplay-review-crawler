---
phase: 6
title: "Validation, migration, and rollout"
status: in_progress
priority: P0
dependencies: [phase-02, phase-03, phase-04, phase-05]
---

# Phase 6: Validation, migration, and rollout

## Overview

Ship the refactor without losing the current dataset or CLI behavior. Validate the worker, queue, limiter, analytics, and UI together, then document the local operating model.

## Requirements

- Functional: old SQLite databases migrate idempotently; current CLI flags remain usable; interrupted jobs resume.
- Non-functional: test suite is deterministic without network; live smoke testing is opt-in and small.
- Operational: startup, worker restart, backup, pause, retry, and cleanup are documented.

## Architecture

Use additive SQLite migrations with explicit schema versioning or idempotent existence checks. Keep the old direct crawl path available as a CLI fallback until the worker path has passed soak testing. Add a health/status command that reports database path, worker heartbeat, active jobs, and limiter configuration.

## Related Code Files

- Modify: `src/storage/sqlite_store.py`
- Modify: `src/crawl_cli.py`
- Modify: `README.md`
- Create: `src/worker_health.py` or an equivalent CLI health command
- Modify: `tests/conftest.py`
- Create: `tests/test_migrations.py`
- Create: `tests/test_end_to_end_job_flow.py`

## Implementation Steps

1. Run the full unit suite plus worker/queue integration tests against temporary SQLite databases.
2. Test legacy database migration, duplicate enqueue, cancellation, worker crash/lease expiry, and restart/resume.
3. Run a controlled manual smoke test with a small capped crawl and verify the UI/DB counts.
4. Run a multi-app soak test with conservative worker settings and record request/error metrics.
5. Update README with separate commands for the UI and worker, tuning guidance, limitations, and backup instructions.
6. Roll out behind a configuration flag if the current environment needs a gradual transition.

## Success Criteria

- [x] Full deterministic test suite passes.
- [x] A legacy `data/reviews.db` opens without data loss and migrations are safe to run twice.
- [ ] Worker restart and Streamlit rerun do not duplicate or skip review pages.
- [ ] Multi-app queue, rate-limit behavior, analytics freshness, and Mericrawler branding pass the manual acceptance checklist.
- [x] README explains that Google quota/availability is variable and that SQLite/worker deployment is single-host by design.

## Risk Assessment

The largest regression risk is changing checkpoint ownership while adding job state. Keep the transaction boundary explicit, test failure between review upsert and job update, and preserve the existing resume tests before deleting any old path.
