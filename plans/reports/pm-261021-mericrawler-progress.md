## Project Status: 2026-10-21

### Active plan

| Plan | Status | Validation | Next action |
|------|--------|------------|------------|
| Mericrawler multi-app crawling, reliable analytics, and UI refresh | in progress | 60 tests passed; Streamlit + Chrome QA + capped live worker smoke passed | soak metrics |

### Completed this session

- Added additive `crawl_jobs` SQLite schema with active-target uniqueness, atomic claim, leases, heartbeat, cancellation, retry, and progress APIs.
- Added `crawl_worker.py` with two-worker default, shared limiter, cancellation-aware backoff, and restart-safe checkpoints.
- Added typed transport error classification, request event callbacks, adaptive pacing, analytics fingerprinting, timezone/null/dedup handling, and `Other` language grouping.
- Replaced blocking Streamlit crawl action with a multi-line queue form and live queue panel; renamed visible branding to Mericrawler.
- Added migration, queue, worker, limiter, analytics, and branding tests.
- Added cached analytics tables keyed by package fingerprint, cancellation-aware
  incremental sync, and a suggested retry timestamp for throttled jobs.
- Chrome QA verified five visible queue cards, responsive mobile layout, keyboard
  focus outline, reduced-motion CSS, cancel, and retry behavior.
- Analytics now distinguishes empty calendar periods from measured zero-volume
  periods, so missing periods cannot inflate spike baselines.
- Added regression coverage for cancellation during retry backoff and throttled
  jobs exposing a next-retry timestamp.

### Risks / remaining validation

- No live Google request was run automatically; quota, 429/403 behavior, and healthy-case throughput still need a small capped smoke test.
- Multi-app soak metrics remain open; the capped live smoke is complete.
- The queue is intentionally single-host SQLite + worker, not a distributed scheduler.
