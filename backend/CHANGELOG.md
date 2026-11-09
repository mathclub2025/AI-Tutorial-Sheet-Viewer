# Changes in 0.3.0

- Added backend-owned admin/auth APIs, individual revocable sessions, role/ownership
  checks, local admin creation/password reset, user management and audit records.
- Added persistent signed-upload intents, verified immutable document registration,
  PNG/JPEG support, extraction dispatch tasks, document lists/status/downloads.
- Added revision-controlled question/solution edits, explicit solution-sheet mapping,
  review/rejection/archive, separate document publication and approved asset delivery.
- Added optional local embedding contracts, normalized vectors, revision-aware
  pgvector semantic retrieval, durable indexing jobs and bounded retry/lease recovery.
- Added typed forwarding of the new admin/auth routes at the existing API origin.
  Existing student routes and response fields remain; semantic search/assets have
  separate routes. Existing internal dispatch and callback routes remain.
- Fixed repeated terminal callbacks with a new event ID overwriting human edits.
  Old callback receipt hashes remain valid when optional new asset fields are absent.
- Added additive migration `bc0325102026`, OpenAPI exports for both services, setup
  and integration guides, regression/lifecycle tests and an optional PostgreSQL test.

Compatibility: apply migrations before starting v0.3. FastAPI >=0.121 is now required
for committing dependency-owned transactions before sending success responses.
Existing dependency constraints already include a compatible tested version.
Existing `frontend-client` files and all previous tests are unchanged.
Old stored embeddings require reindexing for semantic search. Existing keyword
search does not require embeddings. No AI models, frontend UI or storage credentials
are supplied by this release. See `docs/IMPLEMENTATION_STATUS.md` for validation scope.

# Changes in 0.2.0 (historical)

## New functionality

Filter catalog; authenticated document job lookup; validated completed/failed callbacks; forwarding to the data service with correlated durability ACKs; live dependency readiness; per-process metrics; HTTP body and response limits; IP rate limits; total deadlines; safe read retries and per-service circuit breakers; Windows setup, dependency constraints, mock integration runner, peer schemas and client checks.

## Compatibility notes

- Existing successful search/ask/detail/similar/explain/dispatch response fields and dispatch HTTP 200 remain.
- Errors now consistently use `error`, `message`, `request_id`, `details`, including validation, auth and routing errors. Health readiness has its own status/dependency response.
- IDs must start with a letter or digit and contain only letters, digits, underscore, dot, colon or hyphen. Job keys have at least eight characters. Update external ID mapping if needed.
- `question_id` with nonempty filters is rejected instead of ignoring filters. Empty filter strings and boolean/string JSON limits are invalid.
- Question lookup checks returned identity; search checks filters and deduplicates IDs; similarity removes the selected question.
- HTTP readiness now calls both peers. Peers must return HTTP 200 with `status=ready`; health 200 does not mean an extraction/index job has finished.
- Production requires six distinct credentials of at least 32 characters. In development, the original shared internal token is a fallback for migration.
- The TypeScript client defaults to `credentials=same-origin`; cross-origin cookie gateways must explicitly enable credentials and exact CORS origins on both sides.
- Python provider injection now occurs in application lifespan. Tests must use `with TestClient(app)` or explicitly enter lifespan. QuestionProvider adds `catalog`; DocumentJobProvider adds `get`.

## External integration still required

Real uploads, persistence, document access, OCR and extraction, embeddings, vector/hybrid search, durable job state, callback retries, index updates and stale-document checks remain with Person 2 and the AI team. Student identity/SSO and per-user authorization need the project's identity/gateway integration. This release does not manufacture those services.
