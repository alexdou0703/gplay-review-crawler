# Phase 1 benchmark notes

Date: 2026-10-21

## Deterministic baseline

- Existing crawler and new queue/analytics tests: **60 passed**, no network calls.
- The fake transport seam covers page success, transient failure, gateway/rate-limit
  failure, empty terminal pages, empty pages with a live cursor, exact caps, and
  checkpoint resume.
- Review rows remain deduplicated by `review_id`; `crawl_state` is still written
  with each page and remains compatible with the legacy database migration.

## Measurement fields now available

`RequestEvent` callbacks report package, language, country, attempt, outcome,
elapsed seconds, page size, item count, and retry delay. Queue rows persist the
latest job status, page/fetched/inserted counters, last event, error class/message,
heartbeat, lease, and cancellation state.

## Live benchmark status

A capped live smoke completed on 2026-10-21 against `com.google.android.youtube`
(`en`, max 1): 1 review fetched, 1 inserted, complete. A second smoke queued the
same target through `crawl_worker.py`: the job reached complete with 1 fetched,
1 inserted, and 1 SQLite review row. The worker's conservative defaults remain
two app workers, a one-second shared minimum request interval, jitter, and
adaptive cooldown after throttling; larger throughput changes still need soak
metrics.
