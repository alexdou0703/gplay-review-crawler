---
title: "Mericrawler: multi-app crawling, reliable analytics, and UI refresh"
status: in_progress
created: 2026-10-21
source: user-feedback
---

# Mericrawler roadmap

## Outcome

Turn the current synchronous Streamlit crawler into a resilient local crawling workspace: one browser session can queue and monitor many apps, crawling continues outside the Streamlit rerun, rate-limit behavior is measurable and controlled, analytics is validated against the stored dataset, and the product is branded as **Mericrawler**.

## Original diagnosis (2026-10-21, before implementation)

- `src/app.py:160` runs the complete crawl inside the Streamlit script run. A click blocks that browser session until all requested pages/languages finish.
- `src/crawler/gplay_crawler.py:296` crawls the 22-language sweep sequentially. This is conservative for Google but makes one app especially slow.
- The pinned scraper seam already has its own transport retry/sleep behavior; the project adds another retry/backoff layer at `src/crawler/gplay_crawler.py:139`, so a rate-limited page can wait much longer than the UI communicates.
- SQLite WAL already supports a reader while a writer runs, but there is no durable job queue, worker lease, cancellation state, or cross-job rate limiter.
- `src/analysis/review_analytics.py` is testable and has useful primitives, but the UI still renders a 22-language chart, recalculates on every rerun, and lacks data-quality/coverage signals.
- The previous UI quick-win plan is completed. Its light theme, readable charts, app management, search, and current-app strip are foundations for this roadmap; they should not be reimplemented.

## Phase roadmap

| Phase | Priority | Depends on | Deliverable |
|---|---:|---|---|
| 1. Baseline and observability | P0 | — | Reproducible crawl benchmark and request/job metrics |
| 2. Durable multi-app job system | P0 | 1 | Queue many apps from one tab; worker runs independently |
| 3. Rate-limit and throughput control | P0 | 1, 2 | Single retry owner, adaptive limiter, honest progress/errors |
| 4. Analytics correctness and performance | P1 | 1, 2 | Validated metrics, clearer charts, cached snapshots |
| 5. Mericrawler brand and workflow UI | P1 | 2, 4 | Renamed product and smoother crawl/insight experience |
| 6. Validation, migration, and rollout | P0 | 2–5 | Regression coverage, runbook, safe adoption path |

### Progress on 2026-10-22

Crawl recovery was committed as `ec2ef3c`. The queue UI follow-up implements
persistent waiting notices, FIFO positions, distinct worker/network states,
Crawl/Insights navigation, and preserved review filters/exports. All 104 tests
pass; desktop and 375px navigation were checked with an isolated database.
Phase 5 retains one open keyboard/reduced-motion verification item. Other
phases retain their outstanding benchmark, recovery, and rollout criteria;
this UI slice does not close those broader validation requirements.
See [queue UX report](../reports/pm-261022-queue-ux.md).

The user subsequently supplied AppstoreSpy references. The implemented visual
direction is now white/light-gray with blue accents, a searchable Apps table,
and an on-demand Analytics workspace with shared chart styling and date/language
filters. The suite now passes 111 tests. Desktop and 375px checks confirm charts,
filters, sidebar access and keyboard focus; reduced-motion browser emulation
remains a separate check. See [design guidelines](../../docs/design-guidelines.md).

## Recommended architecture

```text
Mericrawler Streamlit UI
  ├─ enqueue / cancel / retry jobs
  ├─ poll SQLite job status and current dataset
  └─ render Reviews and Analytics for selected app
             │
             ▼
SQLite queue + reviews.db (WAL, transactional checkpoints)
             │
             ▼
Dedicated worker process
  ├─ claims jobs with a lease
  ├─ runs one job per worker slot
  ├─ persists page + cursor + progress together
  └─ shares a global Google request limiter
```

The initial safe default is two concurrent app jobs, with languages within a job still sequential. Raising concurrency becomes a measured configuration change, not an accidental burst against Google.

## Cross-cutting acceptance targets

- Queue at least five apps in one Streamlit tab without the page becoming blocked.
- Every app waiting for a crawl slot shows a persistent notice naming the apps
  currently crawling and explaining automatic start when a slot opens; queue
  waiting, network retry, and no-worker states must be visually distinct.
- A worker restart does not lose saved reviews or skip a page; queued/running jobs recover through lease expiry.
- Every job visibly reports queued, running, throttled, partial, complete, failed, cancelled, and retrying states.
- Rate-limited requests, network failures, retries, request latency, and effective throughput are distinguishable in logs and the UI.
- Analytics totals reconcile with SQLite rows for the selected package and clearly label language as a market proxy.
- Existing CLI commands and old databases remain usable during migration.
- `Mericrawler` replaces visible `Dravastudio` branding in page title, header, footer, CSS naming, README, and CLI help.

## Open decisions to validate during Phase 1

- Confirm the supported Streamlit version before choosing native fragment polling versus a small refresh fallback.
- Confirm whether the local deployment will always run a separate worker command or needs an embedded development worker.
- Choose default `max_workers` and minimum request interval from measured 429/error rates, not intuition.
- Decide whether a queued batch shares crawl settings or exposes per-app settings before implementation of the form.

## External technical references

- Streamlit documents one session per app view/browser tab and session state scoped to that session: https://docs.streamlit.io/develop/concepts/architecture/session-state
- Streamlit's `AppSession` owns a `ScriptRunner` and widget state for a connected browser tab: https://github.com/streamlit/streamlit/blob/develop/lib/streamlit/runtime/app_session.py
- The scraper transport currently retries requests internally and sleeps on the Play Gateway error marker; its review pagination also has a per-fetch maximum: https://github.com/JoMingyu/google-play-scraper/blob/master/google_play_scraper/utils/request.py and https://github.com/JoMingyu/google-play-scraper/blob/master/google_play_scraper/features/reviews.py

## Follow-on proposal — 2026-10-23

The [multi-user hosting proposal](../261023-multiuser-hosting/plan.md) builds on
implemented crawl recovery and the table/analytics UI. It proposes authenticated
private datasets, PostgreSQL and separately hosted workers for a future beta;
it does not change the current single-host SQLite runtime. Remaining local
benchmark/recovery criteria above are not marked complete by this proposal.
There is no whole-plan blocking dependency: the new plan reuses committed
features and carries its own isolation, load and restore gates. Its hosted
storage migration must retain the existing checkpoint/recovery guarantees.
