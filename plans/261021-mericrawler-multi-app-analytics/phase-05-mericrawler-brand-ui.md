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

## Architecture

Replace the `Dravastudio`-specific constants/classes in `src/ui_styles.py` with Mericrawler naming or a neutral design-token layer. The visual direction can retain the proven purple/light foundation, but add a more intentional product header, queue status badges, progress summaries, and a clear separation between `Crawl` and `Insights`.

Use text labels such as `Queued`, `Running`, `Waiting`, `Rate limited`, `Partial`, `Complete`, and `Failed` with color as a secondary cue. Keep the package ID and app name together to disambiguate duplicate store titles.

## Related Code Files

- Modify: `src/ui_styles.py`
- Modify: `src/app.py`
- Modify: `.streamlit/config.toml`
- Modify: `README.md`
- Create: `tests/test_branding_refs.py`
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
- [ ] Mobile users can reopen the sidebar and reach the queue/results navigation.
- [ ] Existing UI quick-win acceptance checks remain green.

## Risk Assessment

Branding changes can accidentally become a broad visual rewrite. Keep the scope to naming, hierarchy, status communication, responsive behavior, and the highest-value analytics presentation improvements; do not replace working crawler controls without a clear usability gain.
