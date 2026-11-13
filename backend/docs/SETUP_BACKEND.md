# MathClub backend v0.3 — setup

This release updates the backend only. Its API contracts are independent of any
unfinished website. Existing student endpoints, demo mode, AI answer/explain
orchestration, internal callbacks, database records and storage helpers are retained.

Start with this guide for v0.3. The original DOCX guides and demo scripts are retained
as v0.2 reference material; they do not describe the new admin and worker services.

## 1. Install

Open the extracted `backend` folder in VS Code. Use Python 3.11 or 3.12.
In Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e ".[test,embeddings]"
Copy-Item .env.example .env
```

On macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -c constraints.txt -e '.[test,embeddings]'
cp .env.example .env
```

Activate the environment if desired, or replace `python` in the following commands
with its complete path. Run commands from the `backend` directory. Do not overwrite
an existing `.env`; copy the additional settings into it instead.

## 2. Configure services

Edit `.env`. Generate a different secret for each purpose with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

| Setting | Use |
|---|---|
| `API_KEY` | Existing student API credential. Keep it in the website's server/BFF, not browser JavaScript. |
| `PERSON2_SERVICE_TOKEN` and `PERSON2_INBOUND_TOKEN` | The same value on the API and data service. |
| `AI_SERVICE_TOKEN` | Credential accepted by the AI extraction/answer service. |
| `DOCUMENT_DISPATCH_TOKEN` | Shared by the worker and the API's internal dispatch route. |
| `AI_CALLBACK_TOKEN` | AI service uses this to send results to the API. |
| `AI_DATA_TOKEN` | Separate credential for AI document downloads and crop uploads on the data service. |
| `INTERNAL_SERVICE_TOKEN` | API operations/metrics credential. |
| `EMBEDDING_SERVICE_TOKEN` | Credential accepted by the local embedding service. |

`PERSON1_BASE_URL`, `PERSON2_BASE_URL` and `AI_BASE_URL` are origins, without paths.
Set `CORS_ORIGINS` to the actual browser origins when integration begins. Admin login
uses individual accounts; a service API key cannot log in as an administrator.

For production set `APP_ENV=production`, `BACKEND_MODE=http`, and
`CAPTURE_REQUIRED=true`. Replace placeholders with distinct secrets of at least
32 characters. The shared P2 pair is intentionally identical across services.
Use HTTPS at the public ingress and keep internal service routes on trusted network
paths. Leave `CORS_ALLOW_CREDENTIALS=false` for the bearer-token flow.

## 3. Start PostgreSQL and migrate

The existing database is PostgreSQL with pgvector. Docker is one supported way to
start it:

```bash
docker compose -f compose.postgres.yml up -d
python -m alembic upgrade head
```

Set `POSTGRES_PASSWORD` and the matching password in `DATABASE_URL` first. URL-encode
special characters in the connection URL. If the team already has PostgreSQL,
configure that URL instead and ensure the `vector` extension is available. Run the
migration with an account allowed to create the extension, or have the database
administrator create it first.

For an existing installation, back up the database, stop the old API/data workers,
then apply the migration before starting v0.3. Migration `bc0325102026` adds tables
for sessions, upload intents, assets and durable tasks; it adds question revisions,
asset references and embedding revisions. It retains existing rows. Previously
stored vectors have revision zero until explicitly reindexed; existing keyword
search remains usable.

Do not use `Base.metadata.create_all()` as a production upgrade command. The
SQLite database used by tests is not the deployment database.

## 4. Configure private object storage

Fill all four `B2_*` connection fields in `.env`. The storage account needs object
PUT, GET/HEAD and server-side COPY access to the private bucket. Configure the bucket
CORS rules for the future website's actual origins and the signed PUT request.
Supported files are PDF, DOCX, PNG and JPEG, up to 50 MiB by default.

Bytes go directly to a short-lived signed URL. Confirmation checks remote size,
declared content type and the SHA-256 digest of the downloaded bytes. A supplied
checksum must match. The verified object is copied to a different key that has
never had a browser PUT authorization, then verified again. Reusing an old upload
URL therefore cannot overwrite a confirmed document. These checks do not provide
malware scanning or guarantee that a file is a valid mathematical document.

Document confirmation, document registration and job creation are retry-safe. An
expired intent requires a new `client_upload_key`. The original upload staging
objects and unconfirmed abandoned uploads need a periodic retention/cleanup policy;
automatic object deletion is deliberately not performed in this release. Confirmed
objects must be retained while referenced by the database.

## 5. Create the first administrator

```bash
python -m scripts.create_admin --email admin@example.edu --name "MathClub Admin"
```

Enter a password when prompted. There is no default account or password. The
administrator can create reviewer/uploader accounts through the admin API. To
reset an existing account's password, preserving its role and identity:

```bash
python -m scripts.create_admin --email admin@example.edu --reset-password
```

This also revokes its sessions. Existing users with a different password-hash
format need this reset before signing in through the new local authentication flow.

## 6. Start three backend processes

Use three VS Code terminals, each with the same environment and working directory:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
python -m uvicorn app.data_service.main:app --host 127.0.0.1 --port 8001
```

```bash
python -m app.data_service.worker
```

The worker is required. It dispatches extraction jobs and writes embeddings after
review; these tasks are stored in the database and survive process restarts. For
a single diagnostic iteration use `python -m app.data_service.worker --once`.
Multiple PostgreSQL workers use row locks and leases to claim tasks. Restarted
tasks reuse their stable AI job key. Expired workers cannot overwrite newer results.

Open `http://127.0.0.1:8000/docs` for the public/admin API contract. The data service
has its own contract at `http://127.0.0.1:8001/docs`. Admin calls can use port 8000;
the gateway forwards only registered admin/auth routes to the data service.

The existing `Start-MathClub.cmd` and `compose.integration.yml` remain demo tools.
They do not launch this persistent three-process deployment.

## 7. Connect the AI team's actual services

Run the AI extraction/answer service at `AI_BASE_URL`. Follow
`INTEGRATION_CONTRACT.md` for downloads, job identity, terminal callbacks and crops.
The backend does not include the segmentation/CNN/OCR models.

For semantic retrieval choose `EMBEDDING_PROVIDER`. The default `fastembed`
provider generates vectors in-process: install it with
`pip install -c constraints.txt -e ".[test,embeddings]"`, then set
`EMBEDDING_MODEL=BAAI/bge-small-en-v1.5` and `EMBEDDING_DIMENSIONS=384`; the model
downloads on first use. Alternatively set `EMBEDDING_PROVIDER=http` and configure
`EMBEDDING_BASE_URL`, its credential and a stable `EMBEDDING_MODEL` for an external
service implementing `POST /internal/v1/embeddings`. Indexing and queries always
use the same provider, model and dimensions. Changing the model or dimensions
requires a new model identifier and reindexing approved questions. Use
`POST /api/v1/admin/questions/{id}/reindex` for each approved question, with pagination
over the review list. Failed tasks can be retried after configuration is corrected.

Load the bundled question bank into PostgreSQL for local retrieval work with
`python -m scripts.import_question_bank`. The importer is idempotent, groups the
records into synthetic documents by source and year, marks approved questions
public, and queues index tasks. Add `--index` to run the worker until the queue
drains, or run `python -m app.data_service.worker` separately.

Existing `/search` continues keyword retrieval. `/search/semantic` requires the
local embedding service and current approved vectors. It never returns demo or
keyword results disguised as semantic results. `/ask` keeps its original keyword
retrieval behavior for compatibility; semantic context can be selected separately
by the integrating application.

## 8. Verify

```bash
python -m pytest
python -m ruff check app tests scripts
python -m scripts.export_openapi
python -m scripts.export_contracts
```

The normal suite uses persistent SQLite plus controlled AI/object-storage adapters.
For the optional real PostgreSQL test, point `MATHCLUB_TEST_DATABASE_URL` at a
disposable PostgreSQL database with pgvector installed and run:

```bash
python -m pytest tests/test_postgres_integration.py
```

That test creates and drops an isolated schema, applies migrations, preserves a
legacy document, executes pgvector similarity and checks worker claims. It needs
schema-creation permission. Do not point it at the production database.

Complete the real-service acceptance run before deployment: upload a real file,
confirm it, receive real extracted questions, review/edit, approve the question and
solution, publish, run the worker, then verify keyword search, semantic retrieval,
crop display and persistence after restarting all backend processes.

## Troubleshooting

| Symptom | Check |
|---|---|
| Admin endpoints return 503 | Use HTTP mode; start the data service and apply migrations. Demo mode has no persistent administration. |
| Upload confirmation fails | PUT the file bytes first; check byte length, MIME, checksum, expiry and bucket COPY access. Retrying confirmation is safe. |
| Document stays processing | Start the worker; inspect admin tasks and document processing jobs. Then check the AI service and callback credentials. |
| Approved question is absent from keyword search | Publish its document; verify the current version, filters and question status. |
| Semantic results are empty | Check the local model, run/retry the indexing task, and confirm approved vectors match the current revision/model. |
| Update returns 409 | Reload the question and submit its current `revision` as `expected_revision`. |
| Callback retry returns 409 | The same event/job key was reused for different content, identity or version. Do not change accepted terminal results. |
