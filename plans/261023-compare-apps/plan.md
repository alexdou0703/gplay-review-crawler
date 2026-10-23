---
title: Compare saved app reviews
status: completed
priority: P1
---

# Compare apps

User approved the proposed comparison flow on 2026-10-23. Preserve Streamlit,
SQLite and existing single-app analytics; no AI, semantic labels, geography
inference, Sankey, crawling changes, deployment or automatic commit.

## Reviewed implementation scope

- Insights gets Single app / Compare apps modes. Compare selects 2–5 saved apps.
- Inclusive UTC date range, daily/weekly/monthly buckets, one selected metric:
  average rating, 1–2 star share, saved review volume, developer reply share.
- Fixed app colors, shared hover across apps, rating axis 1–5, percentages 0–100.
- Horizontal 100% stacked rating distribution and sortable comparison summary.
- Display per-app saved count, observed date span, latest save, crawl-language
  context and current crawl status. Observed date span is not proof of completeness.
- Missing buckets break lines, missing rating/rates remain unavailable. Counts
  refer only to saved reviews. Valid rated/dated rows form a common denominator.
- Aggregate in SQLite without loading full comment bodies for every selected app.
- No existing storage signatures, database schema or queue controls change.

## Steps

- [x] Aggregate snapshot and pure comparison calculations.
- [x] Compare UI, charts and navigation integration.
- [x] Unit/integration/UI checks, independent review and fixes.
- [x] Documentation and journal.

## Acceptance

Correct weighted averages, percentage denominators, inclusive UTC bounds,
calendar grouping, duplicate-name identity, no-data and sparse periods,
two-to-five app validation, stable colors, refresh/delete/navigation behavior;
existing tests pass. UI inspected on desktop and narrow viewport when available.

## Touchpoints

New storage/comparison_store.py, analysis/app_comparison.py, comparison_ui.py,
comparison_charts.py; app.py and queue_ui.py navigation; dedicated tests;
README and design guidelines. Prior multi-user hosting proposal remains pending.

## Delivery evidence

- Final tester run: 149 tests passed in 4.35s; source compilation passed;
  `git diff --check` clean.
- Independent review: no remaining blocking defect. Fixed filter restoration
  after mode switches and rejected impossible/out-of-range dates before Pandas.
- Browser checks by parent: shared period tooltip, desktop charts, 390px mobile
  layout without document overflow; rating bars and legend fit; viewport reset.
- Details: [validation report](reports/validation.md).
- Journal: [comparison delivery notes](../../docs/journals/261023-compare-apps.md).
