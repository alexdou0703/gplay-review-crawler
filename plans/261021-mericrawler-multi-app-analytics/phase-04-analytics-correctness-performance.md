---
phase: 4
title: "Analytics correctness and performance"
status: in_progress
priority: P1
dependencies: [phase-01, phase-02]
---

# Phase 4: Analytics correctness and performance

## Overview

Turn the Analysis tab into a trustworthy, fast summary of the selected app. Preserve the useful campaign/market/version/reply ideas, but make every number traceable to the stored rows and make large datasets cheap to revisit.

## Requirements

- Functional: provide summary metrics, volume/rating trends, spike explanations, language coverage, version timeline, and developer-reply metrics with explicit sample sizes.
- Correctness: handle timezone-aware timestamps, missing periods, null languages/versions, whitespace replies, duplicate review IDs, and sparse datasets deterministically.
- Performance: avoid recomputing all pandas transforms on every checkbox/poll rerun; invalidate cached analysis when the package's data fingerprint changes.

## Architecture

Keep calculations in `src/analysis/review_analytics.py` and make the UI a renderer. Add a package data fingerprint based on row count and latest `crawled_at`/review timestamp. Cache the prepared frame and derived tables by package/fingerprint/granularity.

Make spike detection explicit about period coverage and baseline sufficiency. Use a baseline that is not contaminated by the spike being classified, expose baseline/sample counts, and keep tone as a qualified signal rather than a definitive campaign/backlash label. Add a top-N language grouping helper that preserves an `Other` bucket and a coverage caption.

The UI should show a compact KPI row first, then a volume/rating chart with separate encodings, a readable top-N market mix with legend selection, version results using an accessible single-hue scale, and reply-rate cards with denominators. Add date-range and granularity controls only after the base numbers reconcile.

## Related Code Files

- Modify: `src/analysis/review_analytics.py`
- Modify: `src/analysis_ui.py`
- Modify: `src/app.py`
- Create: `tests/test_analysis_quality.py`
- Modify: `tests/test_review_analytics.py`

## Implementation Steps

1. Add fixtures for sparse periods, timezone variants, missing language/version, replies containing whitespace, and a known spike.
2. Define and test the data contract for each analytics table: columns, period semantics, null behavior, and reconciliation to raw rows.
3. Fix baseline/tone, language-share, version, and reply-rate edge cases found by the fixtures.
4. Add `Other` grouping and accessible chart encodings; remove emoji from axis titles and use explanatory keys/captions.
5. Add cache/fingerprint invalidation and verify the analysis render with 1k, 40k, and empty/insufficient datasets.

## Success Criteria

- [ ] KPI totals and rating counts match direct SQLite/DataFrame queries for every fixture.
- [x] A missing period is not silently treated as a populated baseline period.
- [x] Market mix is readable with 22 crawled languages and its shares reconcile to the displayed scope.
- [x] Spike header/list counts match and tone labels communicate uncertainty.
- [x] Re-rendering the same dataset reuses cached analytics; a completed job invalidates the cache.
- [ ] The tab has clear empty, insufficient-data, partial-crawl, and stale-data states.

## Risk Assessment

Review language is only a market proxy, not reviewer location. Keep that disclaimer visible. Do not silently infer app releases from review versions; label `first_seen` as a review-based release proxy.
