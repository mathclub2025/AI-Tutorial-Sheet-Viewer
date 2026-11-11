import pytest
from pydantic import ValidationError

from app.config import Settings


def test_health_and_capabilities(demo_client):
    assert demo_client.get("/health/live").json()["status"] == "alive"
    ready = demo_client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["upstream_reachability_checked"] is False
    assert "ask" in demo_client.get("/api/v1/capabilities").json()["features"]
    assert demo_client.get("/openapi.json").status_code == 200


def test_api_key(demo_client):
    assert demo_client.post("/api/v1/search", json={"query": "differentiate"}).status_code == 401
    assert (
        demo_client.post(
            "/api/v1/search", headers={"X-API-Key": "wrong"}, json={"query": "differentiate"}
        ).status_code
        == 401
    )


def test_search_and_filters(demo_client, headers):
    resp = demo_client.post(
        "/api/v1/search",
        headers=headers,
        json={"query": "differentiate", "filters": {"source_type": "tutorial"}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["request_id"] == "mathclub-test-1234"
    assert resp.headers["x-request-id"] == "mathclub-test-1234"
    assert body["items"][0]["question"]["id"] == "demo-calc-01"
    assert body["captured"] is False
    assert all(item["question"]["source"]["source_type"] == "tutorial" for item in body["items"])


def test_ask_with_retrieval_and_citations(demo_client, headers):
    resp = demo_client.post(
        "/api/v1/ask",
        headers=headers,
        json={"query": "Differentiate x^3", "explanation_level": "beginner"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "answered"
    assert data["answer"].startswith("DEMO ONLY")
    assert len(data["citations"]) == 1
    assert data["citations"][0]["question_id"] in [
        h["question"]["id"] for h in data["matched_questions"]
    ]


def test_ask_by_question_id(demo_client, headers):
    resp = demo_client.post("/api/v1/ask", headers=headers, json={"question_id": "demo-la-01"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["citations"][0]["question_id"] == "demo-la-01"


def test_no_match_does_not_fabricate_answer(demo_client, headers):
    resp = demo_client.post(
        "/api/v1/ask", headers=headers, json={"query": "quaternion eigenvector banana unicorn"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "no_matches"
    assert resp.json()["answer"] is None
    assert resp.json()["citations"] == []


def test_question_and_explain_and_similar(demo_client, headers):
    question = demo_client.get("/api/v1/questions/demo-calc-01", headers=headers)
    assert question.status_code == 200
    assert "Differentiate" in question.json()["text"]
    explain = demo_client.post(
        "/api/v1/questions/demo-calc-01/explain",
        headers=headers,
        json={"instruction": "Explain step by step"},
    )
    assert explain.status_code == 200
    assert explain.json()["citations"][0]["question_id"] == "demo-calc-01"
    similar = demo_client.get("/api/v1/questions/demo-calc-01/similar?limit=2", headers=headers)
    assert similar.status_code == 200
    assert all(h["question"]["id"] != "demo-calc-01" for h in similar.json()["items"])


def test_missing_and_invalid_requests(demo_client, headers):
    assert demo_client.get("/api/v1/questions/missing", headers=headers).status_code == 404
    assert demo_client.post("/api/v1/ask", headers=headers, json={}).status_code == 422
    assert (
        demo_client.post("/api/v1/search", headers=headers, json={"query": "  "}).status_code == 422
    )
    assert (
        demo_client.post(
            "/api/v1/search", headers=headers, json={"query": "limits", "limit": 100}
        ).status_code
        == 422
    )
    assert (
        demo_client.get(
            "/api/v1/questions/demo-calc-01/similar?limit=30", headers=headers
        ).status_code
        == 422
    )
    assert (
        demo_client.post(
            "/api/v1/ask", headers=headers, json={"query": "probability", "unknown_field": 1}
        ).status_code
        == 422
    )


def test_cors_is_restricted(demo_client):
    good = demo_client.options(
        "/api/v1/ask",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )
    assert good.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = demo_client.options(
        "/api/v1/ask",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert bad.headers.get("access-control-allow-origin") is None


def test_production_fail_closed():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", backend_mode="demo", api_key="secret")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            backend_mode="http",
            api_key="secret",
            person2_base_url="http://localhost:8001",
            ai_base_url="http://localhost:8002",
        )
