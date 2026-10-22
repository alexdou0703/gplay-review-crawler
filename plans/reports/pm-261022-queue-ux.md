# Queue UX implementation — 2026-10-22

Implemented the user's waiting-notification requirement in Phase 5. Each
eligible queued app shows its FIFO position and persistent notice naming the
currently processing apps. Missing/stale worker heartbeats and network backoff
have separate explanations. Notices update with queue polling without repeated
popups or invented completion estimates.

The queue reads all active jobs separately from bounded history. Crawl and
Insights navigation includes Open reviews, selected-app context, explicit
refresh, and saved partial-result messaging. Search/rating filters and filtered
CSV/JSON exports survive switching workspaces. Worker scheduling and concurrency
are unchanged.

## Validation

- 104 tests passed in 1.84 seconds after the final CSS fixes.
- Independent code review resolved filter persistence and active older-retry
  selection issues; its follow-up found no further blocking issues.
- Chrome desktop and 375px checks used an isolated five-job fixture database.
  Verified persistent notices, responsive cards, Open reviews selecting YouTube,
  and sidebar reopening. Found and fixed toolbar hiding of the sidebar expander
  in the installed Streamlit version; corrected doubled caption fading.
- Final browser keyboard/reduced-motion rerun remains open because the test
  window became unavailable. Existing focus/reduced-motion CSS is retained.

## Roadmap audit

Phase 1 still needs controlled latency attribution. Phase 2 still tracks process
kill/restart and cancellation acceptance. Phase 3 still needs comparative
throughput/error-rate soak measurements. Phase 4 retains broader KPI/state
validation. Phase 5 implementation is delivered with the accessibility rerun
above open. Phase 6 retains migration/restart and full rollout acceptance.
No broader phase is marked complete by this UI-only follow-up.

## Lessons

Conditional Streamlit screens can remove widget state; persist preferences
outside widget keys. Latest-created job is not necessarily the active attempt
when users retry older jobs. CSS that hides framework containers must account
for controls nested inside them, and browser verification is needed to catch
those compatibility changes.
