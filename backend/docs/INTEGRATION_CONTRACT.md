# MathClub backend integration contract — v0.3

This contract belongs to the backend. No frontend ZIP was used to define its route
names or payload shapes. Base URL examples use `http://127.0.0.1:8000`.
`docs/openapi.json` is the gateway schema; `docs/openapi-data-service.json` describes
the data service and internal AI ingestion routes. JSON schemas are in `docs/contracts`.

## Services and ownership

| Service | Responsibilities | Default address |
|---|---|---|
| API/gateway | Existing student APIs, AI answer/explain orchestration, callback validation, typed admin forwarding | Port 8000 |
| Data service | PostgreSQL records, admin sessions/roles, upload confirmation, review, publication, search and asset authorization | Port 8001 |
| Worker | Durable extraction dispatch and embedding/index jobs with retry/backoff/leases | No HTTP port |
| AI services, supplied by AI team | Segmentation/OCR/extraction, explanations and locally generated embeddings | Port 8002 or configured origins |
| Private object storage | Document and cropped-image bytes | B2 S3 endpoint |

The website team consumes the documented contracts. It owns UI wiring and its
server-side handling of the existing student `X-API-Key`. Internal credentials and
storage account keys must stay on servers. Admin clients use individual bearer
sessions; service keys do not confer an admin role.

## Authentication and roles

`POST /api/v1/auth/login` takes JSON `{ "email": "...", "password": "..." }` and
returns `access_token`, `token_type`, `expires_at` and the user record. Send
`Authorization: Bearer <access_token>` on subsequent admin calls. Sessions expire
after eight hours by default; there is no refresh token. Logout revokes the current
session. Disabling a user or changing their role revokes all their sessions.

| Role | Access |
|---|---|
| Uploader | Authorize/confirm their uploads, list/read their documents/questions, download their assets and request processing |
| Reviewer | Inspect documents/assets, edit and review questions/solutions, publish/unpublish, upload review crops and request reindexing |
| Admin | All uploader/reviewer actions, account administration, task retries and audit events |

There is no public registration or student identity directory in this release.
The existing student gateway credential is preserved. Never store that shared key
in the browser bundle; an integrating site's server can hold it.

## Existing routes retained

| Method/path under `/api/v1` | Existing behavior |
|---|---|
| `GET /catalog` | Valid filter combinations |
| `POST /search` | Keyword retrieval with existing request/response shape |
| `GET /questions/{id}` | Approved public question and approved solution text |
| `GET /questions/{id}/similar` | Existing similar-question retrieval |
| `POST /ask` | Existing retrieval + AI answer orchestration |
| `POST /questions/{id}/explain` | Existing AI explanation orchestration |

Example student search, sent by the website server using `X-API-Key`:

```json
{
  "query": "mean median mode",
  "filters": {"subject": "Probability and Statistics", "source_type": "tutorial"},
  "limit": 5
}
```

The response remains `{ "items": [{ "question": {...}, "relevance_score": 0.8 }],
"total": 1, "request_id": "...", "captured": true }`. `total` is the number of
returned matches, not a whole-corpus count. Source types remain `tutorial`, `pyq`
and `practice`. Filter names remain `subject`, `module`, `topic`, `year`, `source_type`.

## Upload and document lifecycle

1. `POST /api/v1/admin/uploads` with the following metadata:

```json
{
  "client_upload_key": "semester1-calculus-001",
  "filename": "calculus.pdf",
  "content_type": "application/pdf",
  "size_bytes": 125000,
  "title": "Calculus tutorial 1",
  "document_type": "tutorial_sheet",
  "source_type": "tutorial",
  "subject": "Engineering Mathematics",
  "module": "Calculus",
  "year": 2026,
  "process": true
}
```

An optional 64-character hex `sha256` binds the uploaded bytes. `document_type` can
be `question_paper`, `tutorial_sheet`, `answer_sheet` or `other`. Use `process=false`
for an `answer_sheet`; answer sheets are mapped explicitly during review, rather
than treated as a new list of questions.

2. Read the returned upload `id`, `upload_url`, `required_headers` and `expires_at`.
   PUT raw file bytes to the signed URL. The browser supplies Content-Length itself;
   use the exact file size and Content-Type. Do not send bearer/service tokens to
   the storage URL.
3. `POST /api/v1/admin/uploads/{id}/confirm`, with the same user's bearer token.
   It returns `confirmed=true` and `document_id`. A confirmed retry returns the
   same identifiers, without creating another document/task. No arbitrary object
   key or download URL can be registered as a trusted document.
4. `process=true` creates a durable dispatch task. The separate worker submits it
   to the existing `/internal/v1/documents/dispatch` API. Documents start private.
5. Poll `GET /api/v1/admin/documents/{document_id}` and its `/processing-jobs` route.
   Dispatch-task success means the AI accepted a job; it does not mean extraction
   finished. Terminal callback persistence updates document processing status.

For an uploaded, unprocessed document use `POST /admin/documents/{id}/process` with
the existing `DocumentDispatchRequest` fields: document ID/version, source type and
a stable `client_job_key`. A failed dispatch must be retried using its existing
task. After an AI job reports a terminal extraction failure, a deliberate new
processing request can use a new job key. A successfully extracted document is
not automatically re-extracted over reviewed content.

Lists use `offset` (default 0) and `limit` (default 20, maximum 100). Document and
question lists return `items`, `total`, `offset`, `limit`.

## AI handoff

The original extraction job submission/status/terminal callback contracts remain.
AI must deduplicate `client_job_key` and return the same `job_id` for a replayed
submission. The AI service must report terminal status before sending its terminal
callback, because the API validates the callback against the AI's status endpoint.

1. AI receives a document ID/version in its existing `POST /internal/v1/document-jobs`.
2. With `X-Internal-Token: <AI_DATA_TOKEN>`, call the **data service**:
   `GET /internal/v1/ingestion/documents/{id}?document_version=v1`.
   It returns metadata, a short-lived source download URL and its expiry.
3. Extract questions and, optionally, crop question/solution images. Authorize each
   crop using `POST /internal/v1/ingestion/assets/uploads` with an `AssetUpload`
   body (file metadata, stable upload key, document ID/version and `kind` equal to
   `question_image` or `solution_image`). PUT the bytes, then confirm through
   `/internal/v1/ingestion/assets/uploads/{id}/confirm`. Keep the returned `asset_id`.
4. In the existing terminal result, an extracted question can include optional
   `question_asset_id` and `solution_asset_id`. Both must be confirmed assets of the
   correct kind/document/version. Old payloads without these fields remain valid.
5. Send the existing terminal callback to the **API service**:
   `POST /internal/v1/document-jobs/{job_id}/result`, using `AI_CALLBACK_TOKEN`.
   Preserve event/job identity, document version and source metadata. Successful
   callbacks persist `pending_review` questions/solutions; AI cannot self-publish.

Replaying the same result, even with a new event ID, does not overwrite reviewed
edits. Different content under an already accepted event/job identity returns 409.
The callback's indexing acknowledgement describes acceptance; use document/task
status for the current indexing state.

## Review, solutions and publication

| Operation | Endpoint |
|---|---|
| List review queue | `GET /api/v1/admin/questions?document_id=...&status=pending_review` |
| Read one review item | `GET /api/v1/admin/questions/{id}` |
| Edit content/mapping | `PATCH /api/v1/admin/questions/{id}` |
| Approve, reject, flag for review or archive | `POST /api/v1/admin/questions/{id}/review` |
| Publish or unpublish a document | `POST /api/v1/admin/documents/{id}/publication` |
| Preview a source document | `GET /api/v1/admin/documents/{id}/download` |
| Upload a crop as a reviewer | `POST /api/v1/admin/assets/uploads`, then the common upload-confirm endpoint |
| Preview an uploaded crop | `GET /api/v1/admin/assets/{id}/download` |

Every edit/review request includes the last returned `expected_revision`:

```json
{"expected_revision": 1, "text": "Differentiate x squared", "official_solution": "2x"}
```

Edits return the question to `pending_review`, demote its solutions to review, and
invalidate the old vector immediately. A subject change clears incompatible
module/topic assignments. Missing fields retain their previous values; nullable
fields such as `module`, `topic`, solution text and asset references can be cleared
with explicit null. `text` and `subject` cannot be cleared.

Example approval:

```json
{"expected_revision": 2, "status": "approved", "approve_solution": true, "note": "Verified against the solution sheet"}
```

`approve_solution` defaults to false: approving a question does not silently
approve its solution. To flag an item, submit `status=pending_review` with a note;
the note is stored in the audit log. Other accepted statuses are `rejected` and
`archived`. A 409 revision conflict means another edit/review won; reload the item.

For a separately uploaded answer sheet, patch `solution_document_id` to that
document ID and set `official_solution` and/or a confirmed `solution_asset_id`.
The solution crop must belong to the selected answer-sheet document and version.
Question crops must belong to the question's own source document. Review this
mapping before approving the solution. Automatic matching of separate answer
sheets is an AI-team feature; the backend supplies the explicit persistence path.

Publish using `{ "visibility": "public" }`; unpublish using `private`. Student
search requires an approved question on a public document, and excludes old
document versions. Publication never auto-approves questions. Approved content
can be indexed while its document is private; publication controls student access.

## Semantic search and images

`POST /api/v1/search/semantic` accepts the normal search fields plus optional
`min_score` in [0,1], default 0.7. The default was raised from 0.2 after
evaluating BAAI/bge-small-en-v1.5 on the bundled question bank: on-topic top
similarities measured 0.81-0.89 while unrelated queries peaked at 0.54, so 0.7
separates them. Re-evaluate this value whenever the embedding model changes and
override it per request when needed. It returns the existing `SearchResponse` shape.
The query is split into sentence-based chunks: short queries stay a single chunk,
empty chunks are discarded and at most 8 chunks are embedded per request. Each
chunk is embedded independently with the configured provider and searched
separately over approved, public, current-revision vectors with the same model
identity and requested filters, keeping up to 10 candidates per chunk. Results
are merged by question ID, each question keeps its maximum cosine similarity
across chunks, and the top results are returned with that score. The initial
implementation uses exact pgvector distance ordering. A model-specific ANN index
has not been added.

On approval, the worker embeds question text, subject/module/topics and approved
solution text. Vectors are checked for expected dimensions and finite, nonzero
values, then normalized before storage. The AI team implements:

```http
POST /internal/v1/embeddings
X-Internal-Token: <EMBEDDING_SERVICE_TOKEN>
Content-Type: application/json
```

```json
{"texts": ["Differentiate x squared"], "model": "mathclub-local-v1", "request_id": "..."}
```

```json
{"model": "mathclub-local-v1", "vectors": [[0.1, 0.2, 0.3]]}
```

The three-dimensional response above illustrates the shape only. Each real vector
must have exactly `EMBEDDING_DIMENSIONS` values (384 by default), and there must
be one vector per input text in the same order. Model name must match exactly.

Embeddings come from `EMBEDDING_PROVIDER`. The default `http` provider posts to
the endpoint above. The `fastembed` provider generates vectors in-process from
`EMBEDDING_MODEL` (BAAI/bge-small-en-v1.5 with 384 dimensions) and never calls
that endpoint. Indexing and queries always use the same provider, model and
dimensions.

`GET /api/v1/questions/{id}/assets` uses the existing student API key and returns
`question_image_url`, `solution_image_url`, `solution_document_id` and
`expires_in_seconds`. A pending/rejected solution does not get a public solution
image link. Existing `Question` JSON fields are preserved; consumers can call this
additional asset endpoint when rendering crops. Re-fetch after links expire.
Already issued signed URLs remain valid until their short expiry even after an
item is unpublished; new asset requests enforce the current publication state.

## Operations and errors

Admins can inspect `/admin/tasks` and `/admin/audit-events`. Only failed tasks may
be retried through `POST /admin/tasks/{id}/retry`. Indexing retries are also available
through `/admin/questions/{id}/reindex`. The default worker retries five times with
backoff, then requires intervention. It stores error codes, not credentials or
raw exception payloads. Run the worker under a process manager in deployment.

The error envelope is `{ "error": "CODE", "message": "...", "request_id": "...",
"details": [] }`. Common statuses: 401 missing/expired login, 403 wrong role/owner,
404 missing item, 409 stale revision or conflicting idempotency key, 410 expired
upload, 422 invalid input, 429 rate limit, 502 failed object/upstream verification,
and 503 unconfigured/unavailable service. Mutation retries must reuse the original
upload/job/event keys. A request ID is a trace identifier, not an idempotency key.
