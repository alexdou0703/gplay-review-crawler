# Public hosting needs tenant isolation first

**Date**: 2026-10-23 09:48
**Severity**: High
**Component**: Storage, authentication, crawl scheduling, hosting
**Status**: Ongoing — planning only

## What Happened

The user requested a beginner-readable plan for multiple users, private data, hosting and cost. Inspection found one global SQLite database and no tenant ownership boundary. A prettier interface does not make this a public multi-user service.

## The Brutal Truth

The user already struggled with stalled crawls and confusing progress. Publishing the same global data model would add a worse problem: users could share visibility and destructive operations unintentionally. That is a frustrating gap between a usable demo and a service we can responsibly open to others; no production incident was established here.

## Technical Details

`src/storage/sqlite_store.py` keys `apps` by `package_id` and reviews by `review_id`; neither carries workspace ownership. `src/app.py` calls `delete_package(entry_pkg, DB_PATH)` against the shared database. Proposed beta core cost is about **$45/month**, with **$55–75/month** reserved; assumptions and official sources are in [cost research](../../plans/261023-multiuser-hosting/research/costs.md), not measured capacity claims.

## What We Tried

Planning tooling hit an unrelated compatibility failure: installed CK 3.35 lacked the plan command. Temporary `npm exec` with 4.5.2 supplied it; no global upgrade was performed. No migration or load test was attempted.

## Root Cause Analysis

The current schema models a shared local library. Adding login alone cannot establish data ownership, authorize deletes, isolate caches or allocate crawl slots fairly.

## Lessons Learned

Propose retaining Streamlit, moving identity/data to Supabase Auth/PostgreSQL, and separating Railway web and worker processes. Reject a full Cloudflare rewrite for this beta because it adds runtime migration work without demonstrated savings. PostgreSQL replaces the shared-file dependency, but authorization and fairness still require implementation and adversarial tests.

## Next Steps

- User: review budget, audience and retention before implementation scope is finalized.
- Implementer: add workspace ownership and authorization, then fair queue limits and bounded analytics; follow the [plan](../../plans/261023-multiuser-hosting/plan.md).
- Before public beta: test cross-user access denial, restore backups and benchmark concurrent sessions with crawl limits. No approval, paid provisioning, deployment or benchmark occurred during this planning task.
