# Integration implementation map

## Frontend boundary

`src/app/api/backend/[...path]/route.ts` is an allowlisted same-origin server gateway. Student API keys never enter client JSON/bundles. Staff bearer sessions are kept in HttpOnly cookies; mutation requests require the configured Origin. Internal/backend operational routes are not exposed by this gateway. `api/assets/[id]` checks the staff session and obtains fresh authenticated asset redirects.

`src/lib/api.ts` handles structured errors. `adminApi.ts` maps documents to batches, follows backend pagination, manages signed uploads with stable keys, handles typed edits/reviews, and uses durable document/asset IDs. `studentApi.ts` validates search responses and maps them to the existing cards; no automatic mock fallback remains. `NEXT_PUBLIC_SEARCH_MODE=semantic` selects semantic search after the model/index is ready.

The existing styling/components remain. Functional changes are login/logout, role checks, pending/error handling, processing/index status, explicit publication/solution approval, verified image upload, backend-compatible fields and revision conflicts. Save messages wait for successful persistence. Batch summaries come from the backend rather than silently treating failed requests as empty question lists. List adapters retrieve all server pages before applying the existing local filters; very large deployments should add page navigation and server-side filter/search controls.

Chat history retains question identifiers rather than durable solution/image snapshots. Cards and copy/share refresh current public data. Previously stored data is migrated on the next normal history save; already downloaded content cannot be revoked retroactively.

## Backend additions

- Existing topic relation supports multiple editable topics; singular `topic` remains compatible.
- Nullable question difficulty and flag reason use migration `d104_portal_metadata`.
- Review responses expose topics, difficulty, flag reason, document version/source/year.
- Student question contracts expose topics, difficulty and marks without invented defaults.
- Document summaries expose total/approved/flagged/pending counts.
- Classification correction is a reviewer/admin operation with expected-source checks; it unpublishes and invalidates affected content/indexes.
- Login throttling is account-scoped so unrelated users behind the gateway do not share one ten-attempt login bucket. Existing process-wide service limits remain; production should add shared edge limits.
- Portal upload requests are limited to 15 MB.

## Team handoff

Frontend: configure only the website server origin/key and search mode. Do not call private service routes.

Data/storage: provision PostgreSQL+pgvector and B2, apply all migrations, create staff accounts, configure B2 CORS and retain private storage access.

AI team: implement the documented dispatch/status/callback contract, source download/crop-confirmation flow and embedding contract. Preserve stable job/event keys and document versions. Extraction cannot approve or publish its own content.

Operations: run the API, data service, worker and website separately. Monitor task failures, configure HTTPS, rotate sample credentials and apply shared rate limits. Local preview credentials must never be used in production.

## Scope limits

Real PostgreSQL locking/migrations, B2 behavior and AI quality still need acceptance against provisioned services. No student SSO/cloud history, automatic answer-sheet matching, ANN tuning, or deployment is claimed. Existing backend operational endpoints remain available to authorized administrators through its documented API; a new operations dashboard was not added.
