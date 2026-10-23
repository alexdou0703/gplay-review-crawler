# Compare apps: honest statistics need reliable state

**Date**: 2026-10-23
**Severity**: Medium
**Component**: Comparison analytics, Streamlit state, SQLite aggregation
**Status**: Resolved locally; uncommitted and not deployed

## What happened

Added an independent **Insights → Compare apps** mode for 2–5 saved apps.
It compares average rating, 1–2 star share, saved review count and developer
reply rate over time, alongside rating distribution, summary and coverage
tables. The user explicitly chose statistics over AI interpretation.

Two defects surfaced before completion. Leaving Compare deleted its widget
state, so returning showed default controls over previously applied results.
SQLite also accepted dates that the comparison should exclude: impossible
calendar dates were normalized, and extreme years could break Pandas.

## The frustrating part

A polished chart can quietly lie while looking completely reasonable. The
controls/results mismatch was especially bad: users would have no reason to
suspect they were reading another selection. Passing serialization tests alone
would not have caught that navigation failure.

## Technical details and root causes

- `test_applied_filters_survive_leaving_comparison` failed because Streamlit
  removes unrendered widget keys. `comparison_ui.py` now restores missing app,
  date and frequency controls from the persistent `compare_applied` settings.
- `comparison_store.py` now requires a real ISO calendar day and a supported
  UTC date range before aggregation. Regression cases cover `2026-02-30`,
  years `0000`/`9999` and numeric Julian dates.
- SQL produces daily aggregates without loading comment bodies. Rates share
  the same valid, rated-and-dated denominator; averages are review-weighted.
- Missing periods remain unavailable and split line segments. Observed date
  spans are not presented as proof of complete crawling.

## Decisions and lessons

Kept the existing Streamlit/SQLite stack and single-app workflow. Deferred AI,
Sankey and country inference because available data does not justify them.
Use durable applied settings separately from ephemeral widgets. Validate dates
before crossing database/library boundaries. Test navigation as well as math.

Final evidence: **149 tests passed**, source compilation and diff checks passed,
independent review found no remaining blocker, and browser checks covered shared
hover plus desktop and 390px layouts. Mobile checks caught cramped chart spacing
and legend layout, which were corrected.

## Next steps

The user reviews the local comparison flow next. The implementing agent commits
or deploys only when requested. Keep the multi-user hosting proposal separate;
this feature does not introduce authentication or per-user data isolation.
