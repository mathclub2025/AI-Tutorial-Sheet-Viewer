# Changes in 0.2.0

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
