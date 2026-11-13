# Extraction Bridge Contract (DRAFT for sign-off)

Status: draft v1, awaiting extraction-team sign-off.
Owner: integration/retrieval team (spec, helper library, boundary tests); extraction team (facade implementation).
Gateway side: **no changes required or permitted** — the contracts below already exist in code.

## 1. Purpose

Adapt the existing synchronous extraction pipeline (`POST /api/v1/papers/extract`,
`app/extraction/api/v1/endpoints/papers.py`) to the asynchronous document-job
contract the gateway already speaks, so that document upload can reach question
persistence without changing any gateway or data-service code.

Non-goals: no changes to the gateway, the data service, the retrieval subsystem,
the pipeline internals, or the public sync endpoint (it stays for standalone use).

## 2. Architecture

```
Person 2 outbox ──► Worker ──► Gateway POST /internal/v1/documents/dispatch
                                     │ DocumentOrchestrator (unchanged)
                                     ▼
Extraction bridge facade  POST /internal/v1/document-jobs        [NEW, extraction team]
   ├─ persist job (queued), return AgentDocumentJobAck{status:"queued", job_id}
   ├─ download document bytes (AI data credential)
   ├─ run existing pipeline async (GeminiMathExtractor + PDFProcessor + ImagePreprocessor)
   ├─ update job status (processing → completed/failed)
   └─ callback: Gateway POST /internal/v1/document-jobs/{job_id}/result
                                     │ validates against authoritative job (unchanged)
                                     ▼
Data Service POST /internal/v1/document-results (unchanged)
   └─ receipts + pending_review QuestionRecords/Answers
Gateway GET /internal/v1/document-jobs/{job_id} ──► bridge facade status endpoint [NEW]
Gateway GET /health/ready ──► bridge facade health endpoint [NEW]
```

## 3. Endpoints the extraction team must expose

All three require `X-Internal-Token` equal to the gateway's AI service token
(`AI_SERVICE_TOKEN`; gateway sends `token_for("ai_service_token")`,
`app/adapters/http_clients.py`). Constant-time comparison required.

### 3.1 POST /internal/v1/document-jobs — HTTP 202

Request: `AgentDocumentJobRequest` (`app/domain/models.py:200`) =
`document_id`, `document_version`, `source_type`, `client_job_key` (8..128 chars,
`^[A-Za-z0-9][A-Za-z0-9_.:-]*$`), `request_id`.

Response: `AgentDocumentJobAck` = `{"status": "queued", "job_id": "<identifier>"}`.

Idempotency rules (must match `scripts/mock_services.py:77-93`, the reference double):

| Case | Behavior |
|---|---|
| First sight of `client_job_key` | Create job, return 202 with a new stable `job_id` |
| Same key, same identity (`document_id`, `document_version`, `source_type`) | Return 202 with the **same** `job_id` |
| Same key, different identity | 409 (gateway maps this to `UPSTREAM_CONFLICT`) |

A repeated dispatch after process restart must return the same `job_id`
(job state is durable — section 5).

### 3.2 GET /internal/v1/document-jobs/{job_id}

Response: `DocumentJobStatus` (`app/domain/models.py:233-248`). Hard validator rules:

- `status` ∈ {queued, processing, completed, failed}
- `failed` ⇔ `error` present (`JobFailure{code: ^[A-Z0-9_]+$, message}`)
- `completed` ⇒ `progress == 100` and `extracted_count` present
- `queued` ⇒ `progress == 0`
- Unknown `job_id` ⇒ 404
- Identity fields (`document_id`, `document_version`, `client_job_key`,
  `source_type`) must never change for a given `job_id`.

### 3.3 GET /health/ready

`{"status": "ready"}` with HTTP 200 when the job store is reachable, 503 otherwise.
The gateway health check (`app/adapters/http_clients.py:272-307`) accepts only a
200 with `status == "ready"` within the 2 s health timeout. Gemini configuration
is NOT a readiness condition: with `GEMINI_API_KEY` unset the service must still
accept jobs and fail them with `MODEL_NOT_CONFIGURED` (section 8).

## 4. Outbound calls the bridge makes

### 4.1 Document download

`GET {DATA_SERVICE_BASE_URL}/internal/v1/ingestion/documents/{document_id}?document_version={v}`
with `X-Internal-Token: AI_DATA_TOKEN` (`app/data_service/ingestion_api.py:32-44`).
Returns `DownloadView{document: DocumentView, download_url, expires_in_seconds}`.
409 means the version is no longer current → fail the job with
`DOCUMENT_VERSION_CONFLICT`. Then download the signed URL (plain HTTPS GET) and
feed the bytes to the existing pipeline.

### 4.2 Terminal callback

`POST {GATEWAY_BASE_URL}/internal/v1/document-jobs/{job_id}/result` with
`X-Internal-Token: AI_CALLBACK_TOKEN`. Body: `DocumentResult`
(`app/domain/models.py:272-284`) = dispatch identity fields + `event_id` +
`status` + `questions` (≤100 `ExtractedQuestion`) + `error`.

Hard rules (gateway `app/services/documents.py:39-61` + data service
`app/data_service/service.py:276-356`):

1. `completed` requires **at least one question** (`DocumentResult` validator).
   A paper with zero extractable questions must be reported as `failed` with
   code `NO_QUESTIONS_EXTRACTED`.
2. `failed` requires `error` and an **empty** `questions` list; `completed`
   requires `error == null`.
3. `extracted_count` in the status endpoint must equal `len(questions)` in the
   callback for completed jobs.
4. One `event_id` per terminal outcome. If the callback is not acknowledged
   (network error, 5xx), retry with the **same** `event_id` and identical
   content; different content under the same `event_id` is rejected with 409.
   The same terminal payload under a new `event_id` is accepted as a
   receipt-only replay (never re-ingests, never resurrects human edits).
5. Job status is terminal and immutable once completed/failed; the gateway
   re-checks job identity and status against this endpoint before forwarding.

## 5. Job state store (new table — migration approval pending)

Proposed `extraction_jobs` table (single migration, additive):

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| job_id | VARCHAR(128) UNIQUE | External identifier returned by dispatch |
| client_job_key | VARCHAR(128) UNIQUE | Dispatch idempotency key |
| document_id | VARCHAR(128) | External document ID |
| document_version | VARCHAR(100) | |
| source_type | VARCHAR(24) | |
| status | VARCHAR(16) | queued / processing / completed / failed |
| progress | INTEGER | 0..100 |
| extracted_count | INTEGER NULL | Required when completed |
| error_code, error_message | VARCHAR NULL | Required when failed |
| event_id | VARCHAR(128) NULL | Terminal result event ID |
| result_sha256 | CHAR(64) NULL | Replay guard for callback content |
| attempts | INTEGER | Delivery attempts for the callback |
| started_at, finished_at, updated_at | TIMESTAMPTZ | |

No change to existing tables; no gateway or data-service migration.

## 6. Status lifecycle

`queued` → `processing` (when pipeline starts) → `completed` | `failed` (terminal).
Crash recovery: on restart, jobs found in `processing` older than a configured
timeout (recommend 30 min) are marked failed with `EXTRACTOR_CRASHED` and the
callback is emitted. Jobs in `queued` are simply executed.

## 7. Result mapping (needs extraction-team sign-off)

`PaperExtractionResult` / `QuestionItem` → `ExtractedQuestion`
(`app/domain/models.py:255-269`):

| ExtractedQuestion field | Source | Notes |
|---|---|---|
| extraction_id | Stable per question, e.g. `q{index}` | Becomes part of the DB canonical UUID (`uuid5(document_id, version, job_id, extraction_id)`), so it must be deterministic across replays |
| text | `QuestionItem.question_text` | ≤15000 chars; truncate with a review reason if longer |
| subject, module | **Inherited from `DownloadView.document.subject` / `.module`** | NOT from Gemini; the document already carries reviewer-assigned taxonomy |
| topic | null | Reviewer assigns; topic classification is out of scope |
| source.source_type | From the dispatch payload | |
| source.document_id | Dispatch `document_id` | |
| source.document_title | `DocumentView.title` | |
| source.page_number | `QuestionItem.page_number` | ≥1 or null |
| source.question_number | `QuestionItem.question_number` | |
| source.year | `DocumentView.year` | |
| official_solution | `QuestionItem.answer` when `has_explicit_answer` | OPEN QUESTION 7a: subquestion answer composition |
| confidence | `QuestionItem.confidence_score` | |
| needs_review | `QuestionItem.needs_human_review` | All extracted questions persist as `pending_review` regardless |
| question_asset_id / solution_asset_id | null in v1 | Crop persistence to storage is a future extension via the AI ingestion asset endpoints |

## 8. Failure mapping (needs extraction-team sign-off)

| Pipeline condition | JobFailure code |
|---|---|
| `CorruptPDFError`, `EncryptedPDFError`, `InvalidPDFPageError`, `PDFProcessingError` | `DOCUMENT_UNREADABLE` |
| `OversizedPDFError`, `OversizedImageError`, PDF page limit | `DOCUMENT_TOO_LARGE` |
| `UnsupportedFormatError`, `InvalidImageError` | `UNSUPPORTED_FORMAT` |
| `ExtractionTimeoutError` | `EXTRACTION_TIMEOUT` |
| `EmptyModelResponseError`, `MalformedModelOutputError` | `MODEL_OUTPUT_INVALID` |
| `RateLimitExceededError` | `MODEL_RATE_LIMITED` |
| `ProviderAPIError`, `UpstreamServiceUnavailableError` | `MODEL_PROVIDER_UNAVAILABLE` |
| `GeminiConfigurationError` | `MODEL_NOT_CONFIGURED` |
| Unexpected exception | `EXTRACTION_INTERNAL_ERROR` |
| Zero questions extracted | `NO_QUESTIONS_EXTRACTED` |
| Download/version conflict | `DOCUMENT_VERSION_CONFLICT` |

Failed jobs are retried by re-dispatching the document with a **new**
`client_job_key` (the data service already permits this after a failure).

## 9. Configuration additions (`app/extraction/config.py`)

`DATA_SERVICE_BASE_URL`, `GATEWAY_BASE_URL`, `AI_DATA_TOKEN`,
`AI_CALLBACK_TOKEN`, `JOB_TIMEOUT_SECONDS` (recommend 1800), plus reuse of the
existing `GEMINI_*` settings. Local development token values are documented in
`backend/docs/SETUP_BACKEND.md`.

## 10. Delivery plan and acceptance criteria

1. Integration team delivers: a helper library (job store model, ack/status
   serialization, callback client with replay rules) and boundary tests
   (gateway TestClient ↔ bridge TestClient: dispatch → status → callback →
   `pending_review` questions; replay, duplicate-key, crash-recovery cases).
2. Extraction team implements the three endpoints against this spec using the
   helper library.
3. Acceptance: helper tests green; extraction facade passes the boundary suite;
   `GET /health/ready` integrated into gateway readiness shows `ai: true`.
4. Optional live run (separate approval): one test document end-to-end. Requires
   B2 storage configured, `GEMINI_API_KEY`, and an admin account (audit item D2).

## 11. Open questions for sign-off

- 7a: How should subquestion answers compose `official_solution` — parent
  answer only, or parent plus labeled subquestion answers?
- 7b: Confirm subject/module inheritance from document metadata (recommended).
- 8: Confirm the failure-code table.
- 6: Confirm the 30-minute crash timeout and the async execution model
  (in-process thread pool vs subprocess).
- 5: Approve the `extraction_jobs` migration.
