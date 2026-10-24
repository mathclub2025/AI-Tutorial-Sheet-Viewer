import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PAYLOAD = {
    "document_id": "uploaded-p2-doc",
    "document_version": "v1",
    "source_type": "pyq",
    "client_job_key": "upload-idempotency-123",
}


def test_private_document_dispatch_calls_ai_no_file_bytes():
    calls = []

    def fake_ai(request):
        assert request.url.path == "/internal/v1/document-jobs"
        assert request.headers["x-internal-token"] == "p2-ai-shared"
        calls.append(json.loads(request.content))
        return httpx.Response(202, json={"status": "queued", "job_id": "ai-job-123"})

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(fake_ai))
    cfg = Settings(
        _env_file=None,
        app_env="testing",
        backend_mode="http",
        person2_base_url="http://p2.test",
        ai_base_url="http://ai.test",
        internal_service_token="p2-ai-shared",
    )
    with TestClient(create_app(cfg, http_client=upstream)) as client:
        denied = client.post("/internal/v1/documents/dispatch", json=PAYLOAD)
        assert denied.status_code == 401
        res = client.post(
            "/internal/v1/documents/dispatch",
            json=PAYLOAD,
            headers={"X-Internal-Token": "p2-ai-shared"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["job_id"] == "ai-job-123"
        assert calls[0]["document_id"] == "uploaded-p2-doc"
        assert calls[0]["client_job_key"] == "upload-idempotency-123"
        assert "file" not in calls[0]
    asyncio.run(upstream.aclose())


def test_document_dispatch_missing_agent_and_validation():
    app = create_app(
        Settings(
            _env_file=None,
            app_env="testing",
            backend_mode="demo",
            internal_service_token="p2-ai-shared",
        )
    )
    with TestClient(app) as c:
        assert (
            c.post(
                "/internal/v1/documents/dispatch",
                json=PAYLOAD,
                headers={"X-Internal-Token": "p2-ai-shared"},
            ).status_code
            == 503
        )
        assert (
            c.post(
                "/internal/v1/documents/dispatch",
                json={**PAYLOAD, "client_job_key": "a"},
                headers={"X-Internal-Token": "p2-ai-shared"},
            ).status_code
            == 422
        )
