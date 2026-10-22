---
phase: 5
title: "Mericrawler brand and workflow UI"
status: in_progress
priority: P1
dependencies: [phase-02, phase-04]
---

# Phase 5: Mericrawler brand and workflow UI

## Overview

Refresh the product surface around the new queue-and-insights workflow and rename the visible brand to Mericrawler. Keep the already-fixed light theme and readable base components while giving crawl operations and analytics a clearer hierarchy.

## Requirements

- Functional: every visible brand reference says Mericrawler; queue, running, partial, retry, cancel, and completed states are understandable without reading logs.
- UX: one tab can manage many apps, selected-app context remains obvious, mobile/sidebar navigation stays reachable, and destructive actions remain confirmed.
- Accessibility: keyboard focus, contrast, reduced motion, responsive tables/charts, and non-emoji status labels are preserved.
- Queue waiting notifications (user request, 2026-10-22): every app waiting for a
  crawl slot has a persistent inline notice explaining that it will start
  automatically when a slot becomes available, identifying the apps currently
  crawling. Distinguish this from retrying a network request and waiting for a
  worker to become available. Do not invent completion times.

## Implementation slice: queue clarity and navigation (2026-10-22)

- Keep Python/Streamlit, the light purple Mericrawler identity, existing crawl
  controls, review filters/exports, and analytics calculations.
- Present a compact queue summary, then running apps, FIFO pending apps, and
  recent history. Queue positions use the complete active queue, not the latest
  50 jobs sorted by heartbeat; polling must not continually reorder app cards.
- Add a persistent notice on each queued card: "Waiting for a crawl slot.
  Currently crawling: YouTube and Spotify. This app starts automatically when
  a slot opens." Show its position among apps waiting to start.
- If no recently responding worker is observed, explain that the app is waiting
  for a worker instead of claiming other apps are blocking it. A network-backoff
  job still occupies a slot and shows its own retry countdown.
- Keep notifications inline across polling and reloads; do not repeat toasts on
  every refresh. Remove the waiting notice as soon as a job starts or is cancelled.
- Make Crawl / Queue / Insights sections reachable, add an Open reviews action
  from job cards, selected-app context, explicit refresh, and clear empty/partial
  results copy. Preserve the form-submit behavior fixed in the previous commit.
- Scope: UI presentation plus a read-only queue snapshot/helper; no worker
  scheduling, concurrency, database schema, CLI, or analytics algorithm changes.
- Touchpoints: `src/app.py`, `src/ui_styles.py`, a focused queue UI/presentation
  module, read-only SQLite queue queries, tests, README, and this plan.

## Architecture

Replace the `Dravastudio`-specific constants/classes in `src/ui_styles.py` with Mericrawler naming or a neutral design-token layer. The visual direction can retain the proven purple/light foundation, but add a more intentional product header, queue status badges, progress summaries, and a clear separation between `Crawl` and `Insights`.

Use text labels such as `Queued`, `Running`, `Waiting`, `Rate limited`, `Partial`, `Complete`, and `Failed` with color as a secondary cue. Keep the package ID and app name together to disambiguate duplicate store titles.

## Related Code Files

- Modify: `src/ui_styles.py`
- Modify: `src/app.py`
- Modify: `.streamlit/config.toml`
- Modify: `README.md`
- Create: `tests/test_branding_refs.py`
- Create: `src/queue_view.py` and `src/queue_ui.py`
- Modify: `src/storage/sqlite_store.py` (read-only queue snapshot and app status)
- Create: `tests/test_queue_view.py` and `tests/test_queue_ui.py`
- Create: `plans/261021-mericrawler-multi-app-analytics/ui-acceptance.md`

## Implementation Steps

1. Define the Mericrawler name, tagline, palette, status tokens, and logo/header treatment.
2. Replace page title, header, footer, CSS identifiers, copy, and README/CLI references.
3. Redesign the crawl form into a queue-first flow with clear defaults and per-job feedback.
4. Polish queue cards, selected-app context, loading/partial/error states, and analytics hierarchy.
5. Verify desktop, narrow viewport, keyboard focus, and reduced-motion behavior.

## Success Criteria

- [x] `rg -i "dravastudio|drava"` finds no user-facing branding reference except an explicitly documented legacy migration note, if one is needed.
- [x] A user can tell which app is selected while another app is running.
- [x] Queue status is understandable without relying on color or emoji.
- [x] Mobile users can reopen the sidebar and reach the queue/results navigation.
- [ ] Existing UI quick-win acceptance checks remain green.
- [x] With five apps and two running, all three pending apps show an inline
      waiting notice and their FIFO position, naming the running apps.
- [x] Polling moves a newly claimed app into Running and removes its queue notice;
      cancelling a pending app removes it from the waiting count/positions.
- [x] No-worker, expired-heartbeat, request-backoff, partial, and error states
      explain different causes and next actions without a fabricated ETA.
- [x] Active jobs and queue positions remain correct when history exceeds 50 jobs.
- [x] Queue/results navigation and Open reviews work on desktop and 375px width.

## Verification (2026-10-22)

The deterministic suite passes 104 tests (81 existing, 23 added). Queue tests
cover two running plus three pending apps, persisted notices, claim/cancel
transitions, retry countdowns, stale/missing heartbeats, 55 historical jobs,
active retries of older attempts, safe text rendering, and filters/exports
surviving workspace navigation. Browser-only checks are tracked separately in
[UI acceptance](./ui-acceptance.md).

Chrome verification at 375px confirmed wrapped queue notices, reachable actions,
Open reviews selecting YouTube, and reopening the sidebar. The installed
Streamlit nests its sidebar expander inside `stToolbar`; hiding that entire
element removed the control. Toolbar visibility now preserves the expander.
Caption opacity is reset so the chosen text color is not faded a second time.
The current keyboard/reduced-motion browser rerun remains unverified after the
test window became unavailable; the existing focus and reduced-motion CSS is
retained. This phase remains in progress for that acceptance check.

## Risk Assessment

Branding changes can accidentally become a broad visual rewrite. Keep the scope to naming, hierarchy, status communication, responsive behavior, and the highest-value analytics presentation improvements; do not replace working crawler controls without a clear usability gain.

## User-directed AppstoreSpy-style refresh (2026-10-22)

This direction supersedes the earlier purple palette: use the supplied reference
screenshots for a white/light-gray, blue-accent, table-focused workspace while
retaining Mericrawler identity and existing queue notices.

- [x] Replace purple gradients and the dark sidebar with restrained light surfaces.
- [x] Add a searchable Apps table with real saved-review aggregates and navigation.
- [x] Align app/filter controls and give native navigation a tab-like presentation.
- [x] Render Reviews and Analytics on demand rather than calculating hidden tabs.
- [x] Add inclusive date/language filters and daily/weekly/monthly chart grouping.
- [x] Share chart styling across activity, rating distribution, language mix and
      version timeline; retain tooltips, explicit axes, empty and small-sample states.
- [x] Keep queue notices, filters/exports and cancellation/retry behavior covered.
- [x] Verify desktop and 375px chart wrapping, filter layout and sidebar reopening.
- [x] Verify a visible keyboard-focus ring in the browser.
- [ ] Run a browser emulation pass with reduced motion enabled (CSS is retained).

Reference tokens and data conventions live in `docs/design-guidelines.md`.
The deterministic suite passes 111 tests. Browser QA uses a separate fixture
with three apps and 1,544 reviews per app; no production database was changed.
The redesign includes a final-day boundary correction in spike explanations and
cache keys based on filtered DataFrames to avoid cross-app snapshot collisions.
