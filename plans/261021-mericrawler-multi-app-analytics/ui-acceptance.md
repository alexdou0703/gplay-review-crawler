# Mericrawler UI acceptance checklist

- [x] Visible product name is Mericrawler in the page title, header, footer, CSS
      classes, and README.
- [x] Queue input accepts one app per line and shows independent job cards.
- [x] Job cards expose text status, language progress, saved pages/reviews, cancel, retry, and error details.
- [x] Selected package context remains visible while other jobs are queued or running.
- [x] Analysis labels language as a market proxy and groups long language tails into `Other`.
- [x] Queue panel uses native Streamlit fragments when available and a refresh fallback otherwise.
- [x] Manual narrow viewport/keyboard/reduced-motion pass completed in Chrome; focus outline and CSS media rule verified.

## Queue clarity refresh (2026-10-22)

- [x] Five-app batch: two Running, three Waiting for a slot with inline notices
      naming the running apps and showing queue position.
- [x] Waiting notices persist across polling/reload without repeated popups.
- [x] Claim/cancel transitions remove obsolete notices and update positions.
- [x] Network retry countdown differs from slot waiting; absent/stale workers
      show an honest worker-waiting message.
- [x] More than 50 historical jobs do not hide active jobs or corrupt positions.
- [x] Desktop and 375px: sidebar reopens, queue/results navigation works, buttons
      stay reachable, and text wraps.
- [ ] Repeat keyboard-focus and reduced-motion browser checks on the refreshed UI.
- [x] Open reviews selects the correct app; partial/empty results explain what
      is available and how to refresh while preserving filters and exports.

Queue behavior and navigation are covered by `tests/test_queue_view.py` and
`tests/test_queue_ui.py` (104 total tests passing on 2026-10-22). The earlier
checked manual narrow-viewport pass records the previous UI. The refreshed UI
was checked in Chrome at desktop and 375px using a separate fixture database
with five jobs and 12 saved reviews. Open reviews selected YouTube in Insights;
pending cards wrapped without losing actions; the mobile sidebar reopened after
fixing the toolbar CSS. Caption opacity was corrected after visual inspection.
The test window became unavailable before the final keyboard/reduced-motion
rerun, so that check remains open. No production data was changed.

## AppstoreSpy-style refresh verification

- [x] Desktop: light palette, app library navigation, Overview charts render.
- [x] 375px: filters stack, charts fit the viewport, sidebar reopens, Versions
      timeline and review table remain reachable.
- [x] Keyboard Tab focuses a native control with a 3px blue outline.
- [x] Date/language filtering, cache isolation, small-sample charts, library
      totals, unknown-version exclusion and final-day spike details are tested.
- [ ] Reduced-motion emulation (static CSS disables transitions and animations).

Latest deterministic suite: 111 passing tests on 2026-10-22. Chart examples used
isolated demo data, not user reviews or claimed install statistics.
