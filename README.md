# MATHCLUB — integrated website

The original frontend design is retained. `frontend/` contains the Next.js website and a server-side gateway. `backend/` contains FastAPI, the data service, migrations, storage utilities and processing/indexing worker. The original ZIPs in Downloads were not changed.

## Local verification without external services

Prerequisites: Node.js 24 and Python 3.11+ (tested here on Windows with Python 3.14).

From the project directory:

```powershell
py -m venv backend/.venv
cd backend
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e ".[test]"
cd ../frontend
npm ci --ignore-scripts
npm run build
cd ..
.\backend\.venv\Scripts\python.exe scripts/run_website.py --preview
```

Or, after setup/build, double-click `Start-LocalPreview.cmd`.

Open http://localhost:3100. The separate preview backend uses port 8010. Port 3000 is not used, to avoid interfering with an existing application.

**The preview is a test fixture, not real extraction or storage.** It uses the actual backend routes and worker with temporary SQLite, in-memory storage and deterministic AI/embedding responses. An uploaded file produces one clearly labeled sample question; its content is not analysed. Data is discarded when the preview stops. Do not use it with personal or production documents.

Test accounts (all use password `local-test-password`):

- `admin@example.edu`: upload, review and publish.
- `reviewer@example.edu`: review and publish; cannot upload a new source sheet.
- `uploader@example.edu`: upload and inspect owned documents; cannot approve/publish.

Student browsing does not require an account. Chats/bookmarks remain local to the browser. Question content is revalidated before display/copy/share, and expired image links are refreshed.

To verify the full HTTP workflow while the preview is running:

```powershell
cd frontend
node tests/integration.mjs
```

Ctrl+C in the launcher stops the services it started. If a port is occupied, stop the previous preview, not an unrelated application.

## Configure real services

1. Copy `backend/.env.example` to `backend/.env`. Set PostgreSQL credentials, B2 credentials and the AI service addresses/tokens locally. Do not commit or share these files.
2. Start PostgreSQL/pgvector, for example with the backend's `compose.postgres.yml`. Run `backend/.venv/Scripts/python.exe -m alembic upgrade head` from `backend/`. This includes the new `d104_portal_metadata` migration. Back up an existing database first.
3. From `backend/`, run `.venv/Scripts/python.exe -m scripts.create_admin --email YOUR_EMAIL --name "YOUR NAME"` with your actual details, then follow its password prompts. There is no default real admin account.
4. Configure the AI extraction/callback and embedding contracts in `backend/docs/INTEGRATION_CONTRACT.md`. Until embeddings are ready, keep keyword search selected. Approval queues index work; supervise the worker and retry failed tasks after configuring the service.
5. Configure B2 bucket CORS for the exact website origin, allowing browser PUT requests and Content-Type. Keep the bucket private. The effective upload ceiling is 15 MB. The browser sets Content-Length itself and sends no staff/service credentials to B2.
6. Copy `frontend/.env.example` to `frontend/.env.local`. Set `BACKEND_URL=http://127.0.0.1:8000`, `BACKEND_API_KEY` equal to backend `API_KEY`, and `WEBSITE_ORIGIN=http://localhost:3100` for the local launcher. Only `NEXT_PUBLIC_SEARCH_MODE` is public. Never use a public-prefixed environment variable for credentials.
7. Build the frontend, then run `Start-Website.cmd` or `backend/.venv/Scripts/python.exe scripts/run_website.py`. This starts the API (8000), data service (8001), worker and website (3100) as distinct processes. External database/storage/AI services must already be available.
8. Production hosting must provide HTTPS, the exact public WEBSITE_ORIGIN, server-only secrets, supervised services, database backups and suitable shared edge rate limits. Staff cookies are HttpOnly/SameSite=Strict and Secure in production. Do not expose data-service/internal endpoints publicly.

The old `backend/Start-MathClub.cmd` and `compose.integration.yml` remain legacy API/mock utilities, not full-stack launchers.

## Expected workflow

Sign in → upload PDF/PNG/JPEG → wait for extraction → open review batch → edit text/topics/difficulty or replace a verified solution asset → approve the question → separately approve the solution when checked → publish the batch → search as a student → reveal the approved solution.

- Editing returns content/solutions to review and invalidates the index.
- Flag reasons persist and flagged questions are not student-visible.
- Changing the batch source classification unpublishes it and requires review again.
- Solution-image replacement accepts a file, not an arbitrary external URL. Admins can optionally attach a separate answer sheet and its crop in the editor; automatic solution matching is not included.
- Concurrent edits produce a revision conflict rather than overwriting another reviewer.
- Keyword and semantic search are separate; semantic retrieval requires indexed vectors from the configured model.

## Verification and handover

See `verification/REPORT.md` for checks and remaining limitations, `INTEGRATION.md` for the implementation map, and `STARTUP-REVIEW.md` for the removed obfuscated startup additions. The source archives remain the untouched baseline.
