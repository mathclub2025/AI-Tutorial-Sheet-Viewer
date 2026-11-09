# Backend implementation status — 25 October 2026

## Completed in this update

| Area | Implemented behavior |
|---|---|
| Compatibility | Existing student, AI orchestration, callback, query-capture and demo features retained. Existing frontend-client files retained byte-for-byte. |
| Admin identity | Password hashing; persistent, expiring, revocable bearer sessions; uploader/reviewer/admin roles; owner checks; account management and local bootstrap/reset. |
| Uploads | Persistent authorization metadata; retry-safe confirmation; document registration; size/type/checksum verification; separate sealed object keys; PDF/DOCX/PNG/JPEG support. |
| Processing | Transactional dispatch outbox; separate worker; stable AI job keys; persisted processing status; bounded retries/backoff, leases and manual retry APIs. |
| Review | Paginated lists, details, revision-safe edits, approval, rejection, return-to-review notes and archival. Edits invalidate vectors and return answers to review. |
| Publication | Explicit publish/unpublish; student access requires an approved question on a public current-version document. Solution approval is separate and explicit. |
| Question/answer images | Authenticated crop-upload contracts, stored asset IDs, reference validation, reviewer previews, and short-lived approved asset links for students. |
| Separate solutions | Explicit solution-sheet references and text/crop mapping persisted through the review API. |
| Semantic retrieval | Local embedding HTTP adapter, dimensions/model/value validation, normalization, persistent indexing jobs and exact pgvector similarity with filters. Existing keyword search remains separate. |
| Integration | Gateway forwarding of typed admin contracts, separate AI data credential, OpenAPI for both services, JSON schemas, setup guide and team contract. |
| Callback reliability | An identical accepted result with a new event ID creates a receipt without resetting review state or overwriting edited question/solution content. |

## Validation performed

- All 90 pre-existing backend tests passed before the changes.
- The complete Python suite passes with the 19 new lifecycle/embedding cases as
  well as the original tests: **109 passed**. The optional PostgreSQL-specific test
  is skipped unless `MATHCLUB_TEST_DATABASE_URL` is configured.
- New tests exercise both FastAPI services through the real HTTP adapters, a
  persistent SQLite database, a controlled S3 client and controlled AI/embedding
  peers. They cover upload → dispatch → callback → review → publication → indexing
  → search, plus restart persistence, conflicts, permissions, expiry/revocation,
  repeated callbacks, malformed embeddings, failed commits, task retries and stale
  worker/index results.
- Lint, Python compilation, OpenAPI/schema generation and PostgreSQL migration SQL
  generation are checked. No previous tests were edited.

Live PostgreSQL migration/locking and real B2/model behavior have not been verified
in this environment. The optional PostgreSQL test and documented real-service
acceptance flow remain the integration team's final checks.

## What still comes from the other teams or deployment

- The AI team's real segmentation/CNN/OCR/extraction, explanation and local
  embedding models, running behind the supplied service contracts.
- Provisioned PostgreSQL/pgvector and B2 credentials, with a real-service acceptance
  run. Bucket CORS, staging-upload retention and worker supervision are deployment
  configuration tasks.
- Website implementation and UI wiring against these backend contracts. No frontend
  ZIP or frontend code was modified, and no endpoint aliases were added to match
  that work-in-progress UI.
- Automatic matching of separate solution sheets, if desired, belongs to the AI
  workflow. This backend provides explicit, reviewable mapping rather than guessing.
- A large-corpus ANN index and broader relevance evaluation are follow-up work once
  the team's embedding model and dimensions are frozen. Current semantic retrieval
  uses exact pgvector distance ordering.
- Student SSO/account management is separate from the new staff/admin authentication;
  the existing server-side student API-key contract is preserved.

This release completes the backend paths and contracts listed above. It does not
claim that the external AI services or the website have already been integrated.
