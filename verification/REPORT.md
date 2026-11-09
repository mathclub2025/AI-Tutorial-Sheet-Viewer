# Integration verification

Verified on 9 November 2026 on Windows. Frontend and backend remain separate folders; the supplied ZIP archives were not modified.

## Results

| Check | Result |
| --- | --- |
| Backend regression suite | 112 passed, 1 skipped; the PostgreSQL-only test requires a real database |
| Backend and launcher Ruff checks | Passed |
| Alembic PostgreSQL migration SQL generation | Passed through `d104_portal_metadata`; SQL was not applied to a live database |
| Frontend production build | Passed, including TypeScript validation |
| Frontend standalone TypeScript check | Passed |
| Frontend lint | 0 errors, 15 warnings |
| Full HTTP integration against local preview | Passed |
| Browser workflow | Login, review, edit/save, separate question and solution approval, student search and answer reveal verified |
| Combined preview launcher | Started both services and passed the HTTP workflow |

The HTTP checks cover authentication, rejected cross-origin mutations, blocked internal routes, cookie attributes and token omission, signed upload and confirmation replay, stale revision conflicts, persisted flags, separate approvals, publication/search/unpublication, refreshed authenticated asset redirects and image bytes, and logout revocation. See `frontend/tests/integration.mjs` for the executable checks. The browser screenshot is `student-preview.png`.

The backend test run emitted one HTTP client deprecation warning. Frontend lint warnings remain for image optimization, hook/library advice and unused declarations. Dependency review after targeted Next.js/Zod updates found no high or critical advisories and eight moderate development-tooling advisories. These are recorded limitations, not a claim of a completely clean dependency audit.

## What local verification means

The preview exercises actual application routes and worker code with temporary SQLite, in-memory object storage and deterministic extraction/embedding fixtures. It does not validate real AI extraction accuracy, PostgreSQL concurrency or B2 behavior. Uploaded content is not analyzed in preview. Preview data is temporary, and its documented sample accounts are only for local testing.

## Remaining service acceptance

After provisioning the services, follow the root README to configure secrets locally, apply migrations and create a real administrator. Then verify:

1. PostgreSQL/pgvector migrations, transaction behavior and the currently skipped database test.
2. Private B2 storage, browser upload CORS, signed downloads, replacement assets and URL expiry.
3. Real extraction dispatch/callback, retries, document versions and output correctness.
4. Embedding model compatibility, indexing/reindexing and semantic search quality.
5. The complete upload → review → approve → publish → student search workflow under HTTPS with real accounts.

Production deployment and these external-service checks remain pending because the services are not yet available.

## Source handover

`MATHCLUB-integrated-source.zip` contains the separate frontend/backend sources, migrations, tests, launchers and setup documentation. Dependencies, build caches, virtual environments, local secret files and test scratch directories are excluded. Install dependencies and build using the root README after extraction. `CHANGED-FILES.txt` lists modified original files compared with the supplied archives; it is not an exhaustive list of newly added files.
