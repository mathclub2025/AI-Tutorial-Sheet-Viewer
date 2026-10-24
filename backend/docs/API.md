# Public API version 0.2.0

Base path `/api/v1`. The development guard is `X-API-Key: local-dev-secret`. Production browsers must use a trusted authenticated gateway that adds its server-side key. `X-Request-ID` accepts 8–80 ASCII letters/digits/dot/underscore/hyphen; invalid or absent values are replaced. Responses expose the trace header.

| Method and route | Input | Successful result |
| --- | --- | --- |
| GET /catalog | None | combinations[] of subject/module/topic/year/source_type plus request_id |
| POST /search | query, filters?, limit? | items[], total, request_id, captured |
| POST /ask | query and/or question_id, filters?, limit?, explanation_level? | answered/no_matches, answer, citations[], matched_questions[], request_id, captured |
| GET /questions/{question_id} | Path ID | Question |
| GET /questions/{question_id}/similar | limit=1..20 | items[], request_id |
| POST /questions/{question_id}/explain | instruction?, explanation_level? | answer, citations[], request_id, captured |
| GET /capabilities | None; no API key required | mode, features, capture configuration, document orchestration configuration, contract_version |

Search query length is 3–2000 characters. Search limit 1–20; ask context limit 1–10; defaults 5. A selected question can include a query but cannot include non-null filters. Filters use subject/module/topic strings (1–100 characters), year 1990–2100 and source_type tutorial/pyq/practice. Send omitted/null for unused fields, not an empty string. Explanation levels: beginner/standard/advanced. Instruction length 1–1000 if supplied.

`total` is the number of returned hits, not the size of the whole corpus; this contract does not paginate. Catalog combinations are valid joint metadata rows, not independent category arrays; frontend can derive dependent dropdowns. No matches returns HTTP 200, `status=no_matches`, null answer and empty citations. AI is not called in that case.

```json
{"query":"differentiate","filters":{"subject":"Engineering Mathematics I"},"limit":5,"explanation_level":"beginner"}
```

Search/ask/explain record one query intake event before processing. `captured=true` means Person 2 acknowledged intake; it is not an answer history or proof of successful retrieval. Demo returns false. `CAPTURE_REQUIRED=true` prevents proceeding without ACK. Retried user requests receive new event IDs.

## Errors

```json
{"error":"VALIDATION_ERROR","message":"Request does not match the API contract","request_id":"trace-1234","details":[{"location":["body","limit"],"type":"less_than_equal","message":"Invalid value"}]}
```

| Status | Meaning | Frontend behavior |
| --- | --- | --- |
| 401 | Missing/wrong gateway key | Resolve gateway/session configuration |
| 404 | Question or route not found | Show missing content |
| 409 | Internal job/event conflict | Reconcile job/document state; never invent new event IDs to bypass conflicts |
| 413 | Body too large | Reduce payload; no file bytes here |
| 422 | Invalid input | Show field errors |
| 429 | Per-IP limit | Respect Retry-After seconds |
| 500 | Unexpected service failure | Show request ID for support |
| 502 | Invalid/rejected peer response or citation | Report trace to backend team |
| 503 | Missing/unavailable dependency, open circuit, required capture failure | Show temporary unavailable state |
| 504 | Peer timeout or total deadline | Allow user-controlled retry; avoid automatic AI replay |

## Health and private operations

`GET /health/live` returns alive. `GET /health/ready` returns 200 ready or 503 not_ready, mode, dependency booleans and reachability flag. Unconfigured mode returns a 503 error envelope. Demo readiness does not probe real services. HTTP readiness probes both peers.

Private dispatch/status/result and metrics routes are documented in TEAM_INTEGRATION.md and OpenAPI. Do not call them from frontend code. Returned text and URLs are data; render safely. The TypeScript reference adds timeout/cancellation/network error codes with status 0 locally.
