import asyncio
import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

DISPATCH = {
    "document_id": "doc-1",
    "document_version": "v1",
    "source_type": "tutorial",
    "client_job_key": "doc-1-v1-extract",
}
RESULT = {
    **DISPATCH,
    "event_id": "event-1",
    "status": "completed",
    "questions": [
        {
            "extraction_id": "part-1",
            "text": "Differentiate x squared",
            "subject": "Mathematics",
            "source": {"source_type": "tutorial", "document_id": "doc-1", "page_number": 1},
        }
    ],
}
STATUS = {
    **DISPATCH,
    "job_id": "job-1",
    "status": "completed",
    "progress": 100,
    "extracted_count": 1,
}


class Peer:
    def __init__(self):
        self.events = []
        self.job = copy.deepcopy(STATUS)
        self.ack_overrides = {}
        self.sink_status = 200

    def __call__(self, request):
        if request.url.host == "ai.test":
            assert request.headers["x-internal-token"] == "ai-outbound"
            return httpx.Response(200, json=self.job)
        assert request.headers["x-internal-token"] == "p2-outbound"
        self.events.append(json.loads(request.content))
        return httpx.Response(
            self.sink_status,
            json={
                "accepted": True,
                "event_id": "event-1",
                "job_id": "job-1",
                "document_id": "doc-1",
                "document_version": "v1",
                "indexing_status": "pending",
                **self.ack_overrides,
            },
        )


@pytest.fixture
def lifecycle():
    peer = Peer()
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(peer))
    cfg = Settings(
        _env_file=None,
        app_env="testing",
        backend_mode="http",
        person2_base_url="http://p2.test",
        ai_base_url="http://ai.test",
        person2_service_token="p2-outbound",
        ai_service_token="ai-outbound",
        document_dispatch_token="uploader",
        ai_callback_token="ai-callback",
    )
    with TestClient(create_app(cfg, http_client=upstream)) as client:
        yield client, peer
    asyncio.run(upstream.aclose())


def callback(client, payload=None, token="ai-callback"):
    return client.post(
        "/internal/v1/document-jobs/job-1/result",
        json=payload or RESULT,
        headers={"X-Internal-Token": token},
    )


def test_terminal_result_and_replay_forward_same_event(lifecycle):
    client, peer = lifecycle
    for _ in range(2):
        response = callback(client)
        assert response.status_code == 200, response.text
        assert response.json()["indexing_status"] == "pending"
    assert [e["event_id"] for e in peer.events] == ["event-1", "event-1"]
    assert "file" not in peer.events[0]


def test_separate_caller_credentials(lifecycle):
    client, peer = lifecycle
    assert callback(client, token="uploader").status_code == 401
    assert (
        client.get(
            "/internal/v1/document-jobs/job-1", headers={"X-Internal-Token": "ai-callback"}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/internal/v1/document-jobs/job-1", headers={"X-Internal-Token": "uploader"}
        ).status_code
        == 200
    )
    assert not peer.events


@pytest.mark.parametrize(
    "field,value",
    [
        ("document_version", "v2"),
        ("client_job_key", "wrong-key"),
        ("status", "processing"),
        ("extracted_count", 2),
    ],
)
def test_job_identity_or_state_conflict_never_reaches_sink(lifecycle, field, value):
    client, peer = lifecycle
    peer.job[field] = value
    assert callback(client).status_code == 409
    assert not peer.events


@pytest.mark.parametrize(
    "mutation", ["duplicate", "source", "page", "empty", "failed_with_questions"]
)
def test_invalid_extraction_contract(lifecycle, mutation):
    client, peer = lifecycle
    data = copy.deepcopy(RESULT)
    if mutation == "duplicate":
        data["questions"] *= 2
    elif mutation == "source":
        data["questions"][0]["source"]["document_id"] = "other"
    elif mutation == "page":
        del data["questions"][0]["source"]["page_number"]
    elif mutation == "empty":
        data["questions"] = []
    else:
        data["status"] = "failed"
    assert callback(client, data).status_code == 422
    assert not peer.events


@pytest.mark.parametrize(
    "override",
    [
        {"event_id": "wrong"},
        {"document_version": "v2"},
        {"accepted": False},
        {"accepted": 1},
        {"indexing_status": "not_applicable"},
    ],
)
def test_invalid_sink_ack_fails_closed(lifecycle, override):
    client, peer = lifecycle
    peer.ack_overrides = override
    assert callback(client).status_code == 502


def test_failed_job_can_be_reported(lifecycle):
    client, peer = lifecycle
    failure = {"code": "OCR_FAILED", "message": "The document could not be read"}
    peer.job.update(status="failed", progress=40, extracted_count=None, error=failure)
    peer.ack_overrides = {"indexing_status": "not_applicable"}
    data = {**RESULT, "status": "failed", "questions": [], "error": failure}
    assert callback(client, data).status_code == 200


@pytest.mark.parametrize("status,expected", [(409, 409), (503, 503)])
def test_sink_conflict_and_downtime_are_not_acknowledged(lifecycle, status, expected):
    client, peer = lifecycle
    peer.sink_status = status
    assert callback(client).status_code == expected
    assert len(peer.events) == 1  # mutations are never retried inside the gateway
