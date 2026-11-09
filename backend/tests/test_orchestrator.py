from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.models import AgentAnswer
from app.main import create_app


class WrongCitationAI:
    async def answer(self, request):
        return AgentAnswer(answer="Incorrect source", used_question_ids=["unretrieved-id"])

    async def explain(self, request):
        return AgentAnswer(answer="Incorrect source", used_question_ids=["unretrieved-id"])


class ExplodingCapture:
    async def record(self, event):
        raise RuntimeError("DB/storage service temporarily unavailable")


class CountingCapture:
    def __init__(self):
        self.events = []

    async def record(self, event):
        self.events.append(event)
        return True


def test_wrong_agent_citations_fail_closed():
    app = create_app(
        Settings(_env_file=None, backend_mode="demo", app_env="testing"), ai=WrongCitationAI()
    )
    with TestClient(app) as c:
        response = c.post("/api/v1/ask", json={"query": "differentiate"})
        assert response.status_code == 502
        assert response.json()["error"] == "INVALID_AI_CITATIONS"
        response = c.post("/api/v1/questions/demo-calc-01/explain", json={})
        assert response.status_code == 502


def test_capture_acknowledgement():
    events = CountingCapture()
    app = create_app(
        Settings(_env_file=None, backend_mode="demo", app_env="testing", capture_required=True),
        capture=events,
    )
    with TestClient(app) as c:
        response = c.post("/api/v1/ask", json={"query": "differentiate x^3"})
        assert response.status_code == 200
        assert response.json()["captured"] is True
        assert events.events[0].event_type == "ask"
        assert events.events[0].query == "differentiate x^3"


def test_capture_not_required_best_effort():
    app = create_app(
        Settings(_env_file=None, backend_mode="demo", app_env="testing"), capture=ExplodingCapture()
    )
    with TestClient(app) as c:
        response = c.post("/api/v1/search", json={"query": "differentiate"})
        assert response.status_code == 200
        assert response.json()["captured"] is False


def test_capture_required_fails_closed():
    app = create_app(
        Settings(_env_file=None, backend_mode="demo", app_env="testing", capture_required=True),
        capture=ExplodingCapture(),
    )
    with TestClient(app) as c:
        response = c.post("/api/v1/ask", json={"query": "differentiate"})
        assert response.status_code == 503
        assert response.json()["error"] == "CAPTURE_UNAVAILABLE"


def test_unconfigured_fails_closed():
    app = create_app(Settings(_env_file=None, backend_mode="unconfigured", app_env="testing"))
    with TestClient(app) as c:
        assert c.get("/health/ready").status_code == 503
        assert c.post("/api/v1/search", json={"query": "matrices"}).status_code == 503
        assert c.post("/api/v1/ask", json={"query": "matrices"}).status_code == 503
