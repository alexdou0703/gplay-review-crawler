---
phase: 1
title: "Baseline and observability"
status: in_progress
priority: P0
dependencies: []
---

# Phase 1: Baseline and observability

## Overview

Measure the current crawler before changing concurrency or retry policy. The goal is to separate queue wait, Google request time, retry/backoff time, SQLite save time, and analytics render time so later improvements can be judged objectively.

## Requirements

- Functional: record per-request and per-job progress without changing review results.
- Non-functional: metrics must be safe when the worker and Streamlit read/write SQLite concurrently.
- Compatibility: preserve the existing page checkpoint and deduplication semantics.

## Architecture

Add an internal event/metrics model rather than logging only free-form strings. A request event should capture package, language, country, attempt, outcome class, elapsed time, page size, items returned, and retry delay. A job event should capture status transitions, pages, fetched/inserted counts, and error details. Persist only the latest job summary in SQLite initially; keep detailed request logs in structured process logs unless Phase 1 shows a UI need for history.

## Related Code Files

- Modify: `src/crawler/gplay_crawler.py`
- Modify: `src/crawl_service.py`
- Modify: `src/storage/sqlite_store.py`
- Create: `tests/test_crawl_observability.py`
- Create: `plans/261021-mericrawler-multi-app-analytics/benchmarks.md`

## Implementation Steps

1. Capture the current behavior with fake transport tests: one app, all languages, checkpoint resume, a transient error, a gateway/rate-limit error, and an empty page with a live cursor.
2. Add monotonic timing and structured callbacks that do not call Streamlit APIs.
3. Record baseline runs for a small app and a large app using the same language/count settings.
4. Record the time spent in network, backoff, SQLite commit, and pandas/Altair preparation separately.
5. Define the first safe worker and limiter defaults from the baseline.

## Success Criteria

- [x] Existing crawler tests still pass unchanged before the behavior refactor.
- [x] A fake run produces a complete request/job timeline with no secrets or review text in logs.
- [ ] Baseline report identifies whether the dominant delay is request latency, library retry, project backoff, or sequential language work.
- [x] No live Google request is required for the unit test suite.

## Risk Assessment

The scraper uses a private pagination seam, so library upgrades can change error behavior. Pin the dependency during this phase and add a small compatibility test around the adapter before considering an upgrade.
