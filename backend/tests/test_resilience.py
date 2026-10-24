import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.demo import DEMO_QUESTIONS
from app.adapters.http_clients import BaseHTTPAdapter, CircuitBreaker
from app.config import Settings
from app.core.errors import ServiceError
from app.main import create_app


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("timeout", 504),
        ("network", 503),
        ("redirect", 502),
        ("null", 502),
        ("html", 502),
        ("large", 502),
        ("wrong_id", 502),
    ],
)
def test_upstream_failures(kind, expected):
    calls = []

    def handler(req):
        calls.append(req)
        if kind == "timeout":
            raise httpx.ReadTimeout("private detail")
        if kind == "network":
            raise httpx.ConnectError("private detail")
        if kind == "redirect":
            return httpx.Response(302, headers={"location": "https://elsewhere.test"})
        if kind == "null":
            return httpx.Response(200, json=None)
        if kind == "html":
            return httpx.Response(200, text="<html>private detail</html>")
        if kind == "large":
            return httpx.Response(200, content=b"x" * 2048)
        return httpx.Response(200, json=DEMO_QUESTIONS[1].model_dump(mode="json"))

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cfg = Settings(
        _env_file=None,
        app_env="testing",
        backend_mode="http",
        person2_base_url="http://p2.test",
        ai_base_url="http://ai.test",
        upstream_max_response_bytes=1024,
    )
    with TestClient(create_app(cfg, http_client=upstream)) as client:
        response = client.get("/api/v1/questions/demo-calc-01")
        assert response.status_code == expected, response.text
        assert "private detail" not in response.text
        assert len(calls) == (2 if kind in {"timeout", "network"} else 1)
    asyncio.run(upstream.aclose())


def test_read_retry_recovers_but_mutation_is_not_retried():
    async def scenario():
        calls = []

        def handler(req):
            calls.append(req)
            return (
                httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"ok": True})
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = BaseHTTPAdapter("http://peer.test", client, settings=Settings(_env_file=None))
            assert await adapter.request("GET", "/test", "trace1234", retry_safe=True) == {
                "ok": True
            }
            assert len(calls) == 2
            calls.clear()
            with pytest.raises(ServiceError):
                await adapter.request("POST", "/test", "trace1234", json={"event": 1})
            assert len(calls) == 1

    asyncio.run(scenario())


def test_circuit_opens_and_recovers():
    async def scenario():
        calls, healthy = [], False

        def handler(req):
            calls.append(req)
            return httpx.Response(200, json={"ok": True}) if healthy else httpx.Response(503)

        breaker = CircuitBreaker(1, 30)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = BaseHTTPAdapter("http://peer.test", client, circuit=breaker)
            with pytest.raises(ServiceError):
                await adapter.request("POST", "/test", "trace1234")
            with pytest.raises(ServiceError) as caught:
                await adapter.request("POST", "/test", "trace1234")
            assert caught.value.code == "CIRCUIT_OPEN" and len(calls) == 1
            breaker.opened_at -= 31
            healthy = True
            assert await adapter.request("GET", "/test", "trace1234") == {"ok": True}
            assert breaker.opened_at is None

    asyncio.run(scenario())


def test_upstream_filters_enforced_and_duplicates_removed():
    from app.adapters.demo import DemoQuestions
    from app.domain.models import SearchHit

    class BadQuestions(DemoQuestions):
        async def search(self, request, trace_id):
            return [SearchHit(question=DEMO_QUESTIONS[0])] * 3

    cfg = Settings(_env_file=None, backend_mode="demo", app_env="testing")
    with TestClient(create_app(cfg, questions=BadQuestions())) as client:
        assert client.post("/api/v1/search", json={"query": "differentiate"}).json()["total"] == 1
        response = client.post(
            "/api/v1/search", json={"query": "differentiate", "filters": {"source_type": "pyq"}}
        )
        assert response.status_code == 502
