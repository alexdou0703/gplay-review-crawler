# Wider workspace without expanding destructive controls

**Date**: 2026-10-23
**Severity**: Medium
**Component**: Workspace layout, Apps management, responsive charts
**Status**: Resolved locally; uncommitted and not deployed

## What happened

The user removed the Saved apps sidebar and requested a larger, easier-to-read
workspace. App management moved into **Apps**, with explicit Open insights,
Sync reviews and Delete saved app controls. Deletion still requires confirmation.

The content maximum is now 1720px. Root text is 22px, captions 20px, primary
headings reach 40px, controls and table rows are 52px, and chart text is 16px.
The sidebar and its expander are gone rather than merely hidden behind CSS.

## The frustrating part

“Make it bigger” was not just a font change. Enlarging controls exposed date-range
clipping on a 390px screen. Moving existing actions also accidentally made them
reachable for pending apps with zero reviews. A cleaner layout must not quietly
change which records users can mutate.

## Root causes and fixes

- The old sidebar listed saved-review apps, while the Apps library also includes
  pending apps. Moving sync/delete controls without preserving that eligibility
  widened their behavior. Review caught the mismatch. Buttons are now disabled
  without saved reviews, and `sync_library_app` / `delete_library_app` check the
  same condition before performing mutations.
- Larger date inputs did not fit the previous horizontal mobile arrangement.
  The responsive rules in `src/ui_styles.py` stack range fields on narrow screens.
- Larger chart labels needed adjusted axis spacing and greedy overlap handling;
  increasing font size alone made the plots less readable.

## Decisions and lessons

Kept one management surface in Apps instead of duplicating sidebar actions.
Preserved explicit deletion confirmation and the existing saved-review boundary.
Treat UI relocation as a behavior change until the old and new eligible datasets
have been compared. Check actual narrow-screen rendering after typography changes;
desktop screenshots and component tests cannot prove that labels fit.

Validation reported **157 passing tests**, followed by **26 passing chart-targeted
tests** after the final axis tweak. Browser checks confirmed desktop and 390px
layouts, no page overflow, and no sidebar. Evidence is saved at
`/private/tmp/mericrawler-wide-apps.png` and
`/private/tmp/mericrawler-wide-mobile.png`.

## Next steps

The user reviews the wider local workspace next. The implementing agent should
commit or deploy only when requested. Keep the pending multi-user hosting work
separate; this layout change does not establish user isolation or new permissions.
