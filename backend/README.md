# MathClub backend integration service

Version 0.2.0 implements the API and orchestration responsibilities of Backend Person 1. It connects the frontend, the data backend and the AI gateway. Optional PostgreSQL/pgvector schema and Backblaze B2 primitives are now included for an agreed combined deployment; existing routes do not use them and upload authorization remains with the data service.

Start with **docs/MathClub_Setup_Guide.docx**. Use **docs/MathClub_Team_Crossover_Guide.docx** for team integration. The same two guides are also supplied separately.

## Start on Windows

Extract the entire ZIP. Open `mathclub-person1-backend`, double-click `Setup-MathClub.cmd`, then `Start-MathClub.cmd`. Python 3.11+ with the Windows Python launcher and an internet connection for installation are required. Setup creates `.venv`, installs the tested dependency set and creates `.env` only when absent.

Manual PowerShell alternative, without changing execution policy:

```powershell
py -3 scripts/setup.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --no-access-log
```

Open http://127.0.0.1:8000/docs. Select **Authorize** and enter `local-dev-secret` for the public API key. Try `POST /api/v1/ask` with `{"query":"differentiate"}`. Demo responses say `DEMO ONLY` and `captured=false`.

Linux/macOS:

```bash
python3 scripts/setup.py
.venv/bin/python -m uvicorn app.main:app --reload --no-access-log
```

## What changed

- Added a filter catalog for valid subject/module/topic/year/source combinations.
- Completed the private ingestion handoff: dispatch, job status, terminal result validation, and forwarding to Person 2's result sink. Extraction completion and indexing acknowledgement are separate.
- Added live readiness probes, consistent error envelopes, total request deadlines, bounded body/response sizes, per-peer-IP limits and process metrics.
- Added safe read retries, service circuit breakers, credential separation and stricter response identity/filter checks.
- Updated the TypeScript client for catalog lookup, cancellation, deadlines and structured errors.
- Added runnable mock peers, Windows setup/start scripts, dependency constraints, CI configuration and machine-readable peer schemas.

Existing public routes and successful response fields are preserved. Invalid IDs, blank filters and combining `question_id` with filters now fail validation. Error envelopes and production credential requirements changed; see [CHANGELOG.md](CHANGELOG.md).

## Test the handoffs locally

Stop the regular API with Ctrl+C. From a terminal using `.venv` Python:

```bash
python scripts/run_integration_demo.py
```

In a second terminal using the same virtual environment:

```bash
python scripts/check_integration.py
```

The runner starts the API on 8000 and **mock** peers on 8001/8002, all on loopback. It overrides only its child processes' environment and does not edit `.env`. The check verifies capture, dispatch replay, status and callback replay over real HTTP. Mock ACKs are in memory; they prove contract plumbing, not persistence or extraction. Ctrl+C stops the stack.

Optional Docker mock stack: `docker compose -f compose.integration.yml up --build`. Only port 8000 is published to loopback. Stop with `docker compose -f compose.integration.yml down`. Docker was not available for execution in the delivery environment; the Python stack was exercised.

## Connect the actual teams

Adapt `.env.http.example` into your `.env`, then restart. Use `BACKEND_MODE=http`, both service origins and the agreed directional tokens. Each peer must expose `GET /health/ready` returning `{"status":"ready"}`. The included proposed payload contracts must be implemented by the other teams. Never point the mock checker at real document services.

Public browsers use an authenticated same-origin gateway. Keep API and service keys on servers. Student SSO, per-user access control, the public upload/status routes owned by the data backend, durable queues and infrastructure deployment must be completed in the combined project before public release.

## Optional PostgreSQL and B2 infrastructure

See [docs/PERSISTENCE_STORAGE.md](docs/PERSISTENCE_STORAGE.md) for the initial schema, migration workflow, B2 utilities, privacy boundaries, and integration decisions. To run a local PostgreSQL/pgvector service with Docker Compose, set a local-only `POSTGRES_PASSWORD` in `.env`, then run:

```powershell
docker compose -f compose.postgres.yml up -d
python -m alembic upgrade head
```

`DATABASE_URL` must point to the same database. Migration execution and any upload-initiation/confirmation routes require the database credentials and authorization policy agreed with the data-service owner. The B2 credentials in `.env` are optional and must never be exposed to the frontend.

## Run the Person 2 data service

The separate data-service app implements Person 1's documented internal data contracts using the PostgreSQL schema. Configure `PERSON2_INBOUND_TOKEN` to the same secret as Person 1's `PERSON2_SERVICE_TOKEN`, then start it on a separate port:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.data_service.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

Point Person 1's `PERSON2_BASE_URL` at `http://127.0.0.1:8001`. The endpoints are private and require `X-Internal-Token`; do not expose this service directly to browsers. The initial implementation supports search/detail/similar/catalog, query-event persistence, and transactional extraction-result intake. Search is lexical pending the AI team's embedding model/dimension decision. Upload-initiation routes, authenticated reviewer/admin workflows, and durable asynchronous embedding jobs are not included yet.

Run the contract tests with:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests\test_data_service.py tests\test_persistence_models.py -q
```

## Validate and regenerate contracts

Use the virtual environment's Python. Windows command examples use `.\.venv\Scripts\python.exe`; macOS/Linux use `.venv/bin/python`. With the environment activated:

```bash
python -m pytest
ruff check app tests scripts
python scripts/smoke_test.py        # requires a running API with demo sample questions
python scripts/export_openapi.py
python scripts/export_contracts.py
```

For the optional frontend client checks (Node.js 22+):

```bash
npm install --no-save typescript@7.0.2
npx tsc frontend-client/mathclubClient.ts --strict --target ES2022 --lib ES2022,DOM --module commonjs --outDir .client-test
node --test frontend-client/client.test.cjs
```

The check scripts default to localhost. `smoke_test.py` accepts `API_BASE_URL` and `API_KEY`; it bypasses environment proxies for local use. `check_integration.py` is intentionally hardcoded to the local mock stack.

## Contract references

- [Public API](docs/API.md)
- [Cross-team endpoints and ownership](docs/TEAM_INTEGRATION.md)
- [Architecture and flows](docs/ARCHITECTURE.md)
- [Controls and deployment boundaries](docs/SECURITY.md)
- [Validation report](docs/TEST_REPORT.md)
- [Public and incoming internal OpenAPI](docs/openapi.json)
- [Peer payload schemas](docs/contracts/)

`app/domain/models.py` is the source of truth. Contracts are implemented and verified against test doubles here; the real data and AI services have not been supplied or verified.
