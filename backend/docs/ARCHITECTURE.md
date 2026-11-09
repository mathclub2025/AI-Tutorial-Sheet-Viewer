# Architecture

The API coordinates typed Python interfaces. HTTP adapters connect those interfaces to Person 2's data service and the AI team's gateway; injected implementations can run in a combined Python application. Optional PostgreSQL models/migrations and a B2 storage utility are provided for an agreed combined deployment, but the existing routes remain stateless and do not yet use them.

## Student query

1. Apply size/deadline/rate controls, trace ID and gateway-key guard; validate the query.
2. Forward one intake QueryEvent before retrieval or explanation. Required capture stops processing if no ACK arrives.
3. Retrieve questions by filters or selected ID; enforce identity and filter consistency, deduplicate and limit context.
4. If no hits, return `no_matches` without calling AI.
5. Call the AI answer/explanation gateway and require nonempty citation IDs within supplied context.
6. Return answer, citations and capture acknowledgement. Source membership is checked; mathematical correctness remains an AI-team responsibility.

## Uploaded document

1. Person 2 stores the file, versions it and creates the stable document ID.
2. Person 2 calls private dispatch with document ID, version, source type and stable client job key.
3. AI deduplicates submission, persists job state and securely obtains document bytes from Person 2. These operations belong to those services.
4. Person 2 can poll the private job endpoint. AI extraction state is distinct from database ingestion and index readiness.
5. AI persists its terminal state, then sends a completed/failed result callback with a stable event ID. Person 1 checks the authoritative AI job, source-document match, unique extraction IDs and count.
6. Person 1 forwards the event to Person 2 and verifies the ACK identities and indexing status. There is no local queue or persistence.
7. Person 2 validates current document version, atomically deduplicates the event, saves question/solution mappings, queues embedding/index work and ACKs only after its durability boundary. AI retains and retries unacknowledged events.

## Runtime

HTTP clients are opened/closed in lifespan. A shared circuit per peer limits repeated transport/status failures. Only GET retrieval and POST search are retried once by default; mutations are not automatically retried. Total processing deadline defaults to 45 seconds. Readiness probes both peers concurrently under independent 2-second deadlines; liveness is local only.

Request metrics and IP limiter state are bounded/in-process, reset on restart and are not a durable audit log. Multiple workers have independent counters, limits and circuits. Production gateways supply shared per-user controls and student identity. HTTPX environment proxy inheritance is disabled for private peer calls.
