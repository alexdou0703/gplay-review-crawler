---
title: Full-width readable workspace
status: completed
priority: P1
---

# Full-width readable workspace

User requested removal of Saved apps sidebar and larger, clearer layout.

- [x] Remove sidebar rendering; keep open/sync/delete reachable from Apps with explicit labels and delete confirmation.
- [x] Expand main workspace, increase typography/control/table/chart sizing with mobile safeguards.
- [x] Verify navigation, management controls, analytics and responsive layout; update docs.

Scope: app.py, theme, styles, chart styles, affected UI tests and docs. Preserve
crawl/storage/analytics calculations and read-only queue. No commit/deploy.
Acceptance: no sidebar or expander, Apps management still works, empty/deleted
selection handled, readable desktop/mobile, existing behavioral tests pass.

## Delivery evidence

- 157 full-suite tests passed; 26 affected chart tests passed after final label
  spacing adjustment. Source compilation and diff checks passed.
- Independent review found no remaining blocker after preserving saved-review
  eligibility for relocated sync/delete controls.
- Desktop and 390px browser checks passed; both screenshots saved.
- README/design guidelines updated; [journal](../../docs/journals/261023-wide-workspace.md)
  verified. See [validation report](validation.md).
- 3/3 steps complete. No commit or deployment; unrelated plans unchanged.
