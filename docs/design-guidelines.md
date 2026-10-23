# Mericrawler workspace design

The 2026-10-22 refresh follows the user's AppstoreSpy screenshots: a light,
data-focused workspace with compact navigation, horizontal filters and readable
tables. Mericrawler retains its own name and review-based features.

## Tokens and layout

- Canvas `#F7F8FA`, surfaces `#FFFFFF`, dividers `#E3E7EE`.
- Primary text `#172033`, secondary text `#596579`, actions `#2563EB`.
- Be Vietnam Pro for headings and body; monospace package IDs; tabular metrics.
- Flat surfaces, 6–10px corners, no decorative gradients or continuous motion.
- Desktop content up to 1720px with responsive side gutters; columns stack below
  768px. Primary controls are at least 52px high.
- Native controls retain labels, keyboard navigation, focus indicators and
  reduced-motion support. The workspace has no Saved apps sidebar or expander.

## Workflow

Crawl manages submissions and persistent queue notices. Apps lists saved and
pending named apps, searchable by name or package ID. Insights switches between
Single app and Compare apps. Single app selects an app and switches between
Reviews and Analytics. Only the selected view renders; analytics does not run
behind the review table. Apps/Open insights navigation returns to Single app.
Saved-app management lives in Apps: an App to manage selector followed by the
labelled Open insights, Sync reviews and Delete saved app buttons. Deletion needs
an explicit confirmation identifying the app; Keep app cancels it. Changing the
selected app clears the pending confirmation. The Apps table remains read-only.

The Crawl screen uses two numbered surfaces: **Add apps to crawl** and
**Follow crawl progress**. Blue marks the input section and its single, full-width
submit action; a slate border separates the monitoring section. Input borders
must remain visible on white, including both Base Web and React Aria widgets.
The root font and inputs are 22px; supporting copy is 20px. Main headings scale
from 32–40px, section headings are 30px and subheadings 26px (28/24px on narrow
screens). Tables use 52px rows and native theme-sized text rather than a CSS
transform on the canvas. Request delay lives in a collapsed Advanced settings
disclosure. Preserve native form submission, focus states and queue polling;
status meaning never depends on color alone.

Analytics uses an explicit Apply filters form for inclusive UTC dates, languages,
and daily/weekly/monthly grouping. Overview shows KPIs, review activity, rating
distribution and language composition. Versions shows first-seen review dates
for known versions with at least 30 selected reviews. Signals explains volume
spikes without asserting campaigns or incidents as causes.

## Charts and data honesty

Use blue volume bars, teal ratings, amber volume spikes, light grids and readable
tooltips. Rating axes stay at 1–5. Ordered period buckets make sparse monthly
bars visible and keep the time sequence. Language composition supports counts
and percentages; languages outside the top eight appear as Other.

Small samples still render actual data with a caution. Empty selections show a
recovery action. Missing low-rating replies produce an unavailable rate rather
than a misleading zero. Unknown versions are excluded from the version timeline.
Language and country are crawl-query labels, not verified reviewer language or
location. First-seen dates are not release dates.
No install totals or app metadata change events are inferred from reviews.

## Compare apps — 2026-10-23

Use a labelled form for 2–5 saved apps, inclusive UTC dates and daily, Monday–Sunday
weekly or calendar-month grouping. Compare applies the form; retain the applied
filters when returning from Single app. Reject incomplete dates, invalid app
counts and more than 500 periods without leaving stale results under a new filter
heading. Removing a selected app clears the applied comparison.

Layout: full-width trend chart, full-width horizontal 100% rating distribution,
sortable comparison summary, then data-coverage table. Keep exact trend values in
an expander. No metric cards, selectable rows or per-app detail panels are added.
Refresh data reads the latest saved snapshot without creating crawl jobs.

Show one trend metric at a time: average rating, 1–2 star share, saved review count
or developer reply rate. Package IDs distinguish duplicate app names. Preserve
app colors across metric changes; the distribution uses a separate fixed star
palette. Chart axes and legends use 16px text, with comparison chart height
adjusted for app count. Rating axes span 1–5, percentage axes 0–100%. Shared period
tooltips expose each app's value and sample count, plus actual clipped date bounds.

All metrics use valid, supported dates and 1–5 star ratings; averages weight each
review equally. Empty periods break lines and retain unavailable values. Empty
apps remain in the summary with zero reviews and unavailable rates. Coverage
reports all saved counts, excluded rows, oldest/newest observed dates, latest-save
time, query languages/stores and latest recorded crawl status. Those dates do not
prove complete collection. Describe the charts as saved samples, never total
market activity or reviewer geography. SQL aggregates daily counts before the
comparison UI loads data; full comment bodies are not loaded for these charts.

## Runtime

Streamlit 1.47+ is required for the configured root font size, verified in
[the 1.47 theme configuration](https://github.com/streamlit/streamlit/blob/1.47.0/lib/streamlit/config.py).
Restart Streamlit after changing the theme configuration. Live editing while
multiple browser sessions rerun can require a server restart; QA uses an isolated
fixture database and disabled crawl workers.

## Queue table — 2026-10-23

Put shared service guidance above the table once, instead of repeating a warning
inside every queued app. Normal waiting is neutral; amber means a service or
request problem, red means failure and green means completion. Never present past
attempts as successful crawls. Scheduled retries keep their own eligibility time.

The queue is a native sortable table, with one row per crawl attempt, replacing
per-app cards. Columns show app, status, FIFO position, language progress, new
reviews, total saved reviews, next step, package ID, store and submission time.
The table sits directly below its heading, without the refresh
label/button, summary counters or search/filter toolbar. All active requests remain
available; history is bounded to
the latest 20 attempts and the UI states that limit. The table scrolls on mobile.

The table is read-only: no selection checkbox, selected-app panel or per-row
actions. Review navigation lives in Apps and Insights.
The Next step column directs users to Apps when saved reviews are available.
Status colors and progress refresh automatically without requiring row selection.

For isolated UI previews, set `MERICRAWLER_PREVIEW=1` and use a separate fixture
DB with no external worker. This disables the embedded worker and explicitly
labels live crawling as off in the form hint and table rows. The large preview
banner and empty-selection info box are omitted. Do not use preview mode with a production queue or
an external worker. Normal mode never assumes an idle worker is offline; it only
reports the absence of recent active-job heartbeats when eligible jobs are waiting.
