---
title: "UI/UX quick wins from design review"
status: completed
created: 2026-07-30
source: plans/reports/ui-ux-review-260729-2342-streamlit-analysis-app-report.md
---

# UI/UX Quick Wins — single phase

Scope accepted by user: 3 P1 fixes + 12 quick-wins from the design review. OUT of scope this round: P2.4 (top-N lang grouping), P2.8 (sidebar app management/delete), date-range filter, spike-tone tuning (answered: not a bug — Character AI fires `negative` correctly; Block Blast spikes are genuinely organic).

## Changes by file

- `.streamlit/config.toml` — add `[theme]` block: base light, primary #7C3AED, bg #F5F3FF, secondary #FFFFFF, text #1E1B4B (P1.1, root cause of ~8 symptoms)
- `src/ui_styles.py` — restore sidebar collapse control (hide only toolbar/menu/decoration, not whole header; verify testids against running Streamlit version) (P1.2); prune dead `.stCaption` + redundant dark-defensive CSS; `white-space:nowrap` on star pills (P2.7)
- `src/analysis_ui.py` — money chart: rating line purple #7C3AED, normal bars #A5B4FC @0.7, spikes stay red, plain axis titles, colored-key caption (P1.3); spike header "latest X of Y" (P2.1); tone word badges in expander labels (P2.2); markets dict → markdown lines (P2.3); default Monthly granularity (P3.2)
- `src/app.py` — current-app strip (name + pkg + count + last crawl) above tabs, app name in Reviews header (P2.5); keyword search input + Date/Rating `column_config` (P2.6); thousands separators in star pills (P2.7); rename button "Crawl Reviews" (P3.1); plain tab labels (P3.6)

## Validation

- 47 pytest suite green (no analytics behavior change except none — UI only)
- Bare-mode render smoke of analysis tab
- Restart Streamlit (config change requires restart), verify http 200
- code-reviewer subagent pass

## Acceptance

- All captions/radio/metric/dataframe/chart text legible on light theme
- Sidebar reopenable at 375px viewport
- Rating line vs spike bars distinguishable; no emoji in axis titles
- Search box filters review contents; star pills single-line with formatted counts
- App name (not package id) shown in results
