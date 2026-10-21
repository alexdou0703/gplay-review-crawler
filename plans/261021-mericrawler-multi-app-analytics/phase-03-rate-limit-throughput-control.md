---
phase: 3
title: "Rate-limit and throughput control"
status: in_progress
priority: P0
dependencies: [phase-01, phase-02]
---

# Phase 3: Rate-limit and throughput control

## Overview

Make the crawler faster when Google is healthy and calmer when Google is not. The central design rule is one retry owner and one global limiter shared by all concurrent jobs.

## Requirements

- Functional: distinguish throttled, network, parse, not-found, and terminal end-of-history outcomes.
- Non-functional: avoid synchronized request bursts; honor retry hints when available; cap retry time and expose the next retry time.
- Safety: do not add proxy rotation, CAPTCHA bypass, or behavior intended to evade platform controls.

## Architecture

Introduce a transport adapter around the pinned scraper seam. It returns a typed result or error classification instead of forcing the crawler to interpret every exception as throttling. The adapter owns the retry loop; remove the duplicate outer retry behavior or make the lower layer non-retrying, but never keep both policies active.

Place a process-wide token-bucket/min-interval limiter before every review request. Add small randomized jitter, per-host accounting, and an adaptive cooldown: repeated gateway/429/403-like failures lower concurrency and pause new attempts; successful windows gradually restore the configured ceiling. Keep a separate job-level page delay for politeness and make all values configurable.

Persist metrics needed to explain waiting: attempts, retry count, last error class, backoff seconds, pages completed, and effective reviews/minute. A job card should say whether it is queued behind another job, backing off, waiting for the limiter, writing to SQLite, or actively fetching.

## Related Code Files

- Create: `src/crawler/transport.py`
- Create: `src/crawler/rate_limiter.py`
- Modify: `src/crawler/gplay_crawler.py`
- Modify: `src/crawl_service.py`
- Modify: `src/crawl_worker.py`
- Modify: `src/crawl_cli.py`
- Modify: `src/app.py`
- Create: `tests/test_rate_limiter.py`
- Create: `tests/test_transport_errors.py`
- Modify: `tests/test_gplay_crawler_backoff.py`

## Implementation Steps

1. Write a fake transport matrix for gateway marker, HTTP 429/403/5xx-like exceptions, timeout, malformed response, empty page with cursor, empty terminal page, and not-found.
2. Replace the fixed retry chain with exponential backoff plus jitter, a maximum delay, and a clear retry budget.
3. Add a shared limiter around all worker requests and expose `--workers`, `--min-request-interval`, and retry settings in the CLI/config.
4. Add adaptive concurrency/cooldown and make it visible in worker logs.
5. Compare baseline versus controlled runs using the same fixture and, only when appropriate, a small manual live smoke test.

## Success Criteria

- [x] No rate-limit event causes two nested retry loops.
- [x] A transient failure retries and resumes; a persistent throttle becomes partial/throttled with the exact reason and next retry time.
- [x] Concurrent jobs share one limiter and do not each assume they have an independent request budget.
- [x] The worker remains responsive to cancellation during backoff.
- [ ] Benchmarks show improved healthy-case throughput without increasing the rate-limit/error ratio above the agreed threshold.

## Risk Assessment

Google does not publish a stable public quota for this scraping path. Treat 429/403/gateway responses and empty-with-live-cursor responses as empirical signals, keep defaults conservative, and make a pause/resume path first-class.
