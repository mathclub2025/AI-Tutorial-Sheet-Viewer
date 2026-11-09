import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def config(**kwargs):
    return Settings(_env_file=None, app_env="testing", backend_mode="demo", **kwargs)


def test_errors_share_trace_and_do_not_echo_query(demo_client, headers):
    for path, data, status in [
        ("/api/v1/ask", {"query": "private user text", "extra": "secret"}, 422),
        ("/api/v1/ask", {}, 422),
        ("/absent", {}, 404),
    ]:
        response = demo_client.post(path, json=data, headers=headers)
        assert response.status_code == status
        body = response.json()
        assert body["request_id"] == response.headers["x-request-id"]
        assert set(body) == {"error", "message", "request_id", "details"}
        assert "private user text" not in response.text and "secret" not in response.text


def test_api_key_unicode_does_not_crash():
    with TestClient(create_app(config(api_key="secret"))) as client:
        response = client.get("/api/v1/catalog", headers={b"x-api-key": b"\xff"})
        assert response.status_code == 401


def test_body_size_and_cors_on_error():
    with TestClient(create_app(config(max_request_bytes=1024))) as client:
        response = client.post(
            "/api/v1/ask", content=b"x" * 1025, headers={"Origin": "http://localhost:5173"}
        )
        assert response.status_code == 413
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert response.json()["request_id"] == response.headers["x-request-id"]
        assert client.post("/api/v1/ask", content=(b"x" * 600 for _ in range(2))).status_code == 413


def test_rate_limit_cannot_be_bypassed_by_forwarded_header():
    with TestClient(create_app(config(rate_limit_per_minute=1))) as client:
        assert (
            client.get("/api/v1/catalog", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        )
        response = client.get("/api/v1/catalog", headers={"X-Forwarded-For": "2.2.2.2"})
        assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
        assert client.get("/health/live").status_code == 200


def test_internal_metrics_protected():
    with TestClient(create_app(config(internal_service_token="ops"))) as client:
        assert client.get("/internal/v1/metrics").status_code == 401
        body = client.get("/internal/v1/metrics", headers={"X-Internal-Token": "ops"}).json()
        assert body["scope"] == "single_process" and body["requests"] >= 1


class BrokenQuestions:
    async def catalog(self, trace_id):
        raise RuntimeError("private-body-secret")


class SlowQuestions:
    async def catalog(self, trace_id):
        await asyncio.sleep(1)


@pytest.mark.parametrize(
    "provider,status,code",
    [(BrokenQuestions(), 500, "INTERNAL_ERROR"), (SlowQuestions(), 504, "REQUEST_TIMEOUT")],
)
def test_unexpected_and_deadline_errors(provider, status, code):
    with TestClient(create_app(config(request_timeout_seconds=0.2), questions=provider)) as client:
        response = client.get("/api/v1/catalog", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == status
        assert response.json()["error"] == code
        assert "private-body-secret" not in response.text
        assert "x-request-id" in response.headers
        assert "access-control-allow-origin" in response.headers


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cors_origins": "*"},
        {"ai_base_url": "https://user:pass@host"},
        {"person2_base_url": "file:///tmp/x"},
        {"cors_origins": "https://host/path"},
    ],
)
def test_reject_unsafe_configuration(kwargs):
    with pytest.raises(ValidationError):
        config(**kwargs)


def test_production_configuration_requires_separate_credentials():
    values = dict(
        _env_file=None,
        app_env="production",
        backend_mode="http",
        capture_required=True,
        person2_base_url="https://p2.test",
        ai_base_url="https://ai.test",
        **{
            name: str(index) * 40
            for index, name in enumerate(
                (
                    "api_key",
                    "internal_service_token",
                    "person2_service_token",
                    "ai_service_token",
                    "document_dispatch_token",
                    "ai_callback_token",
                ),
                1,
            )
        },
    )
    assert Settings(**values)
    values["ai_callback_token"] = values["document_dispatch_token"]
    with pytest.raises(ValidationError):
        Settings(**values)


@pytest.mark.parametrize(
    "body",
    [
        {"query": "differentiate", "limit": True},
        {"query": "differentiate", "filters": {"topic": " "}},
        {"question_id": "demo-calc-01", "filters": {"year": 2024}},
        {"question_id": "../other"},
    ],
)
def test_ambiguous_and_invalid_inputs_rejected(demo_client, headers, body):
    assert demo_client.post("/api/v1/ask", json=body, headers=headers).status_code == 422


def test_request_id_replaced_if_invalid(demo_client, headers):
    response = demo_client.get("/api/v1/catalog", headers={**headers, "X-Request-ID": "bad id"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] != "bad id"


@pytest.mark.parametrize("ready", [True, False])
def test_live_dependency_readiness(ready):
    def handler(request):
        return httpx.Response(200, json={"status": "ready" if ready else "starting"})

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cfg = Settings(
        _env_file=None,
        app_env="testing",
        backend_mode="http",
        person2_base_url="http://p2.test",
        ai_base_url="http://ai.test",
    )
    with TestClient(create_app(cfg, http_client=upstream)) as client:
        response = client.get("/health/ready")
        assert response.status_code == (200 if ready else 503)
        assert response.json()["upstream_reachability_checked"] is True
        assert client.get("/health/live").status_code == 200
    asyncio.run(upstream.aclose())


def test_actual_chunked_size_limit_without_content_length():
    async def scenario():
        app = create_app(config(max_request_bytes=1024))
        async with app.router.lifespan_context(app):
            chunks = iter(
                [
                    {"type": "http.request", "body": b"x" * 600, "more_body": True},
                    {"type": "http.request", "body": b"x" * 600, "more_body": False},
                ]
            )
            messages = []

            async def receive():
                return next(chunks)

            async def send(message):
                messages.append(message)

            scope = {
                "type": "http",
                "asgi": {"version": "3.0"},
                "method": "POST",
                "path": "/api/v1/ask",
                "headers": [],
                "query_string": b"",
                "scheme": "http",
                "server": ("test", 80),
                "client": ("127.0.0.1", 1234),
                "http_version": "1.1",
            }
            await app(scope, receive, send)
            assert messages[0]["status"] == 413
            assert json.loads(messages[1]["body"])["error"] == "PAYLOAD_TOO_LARGE"

    asyncio.run(scenario())
