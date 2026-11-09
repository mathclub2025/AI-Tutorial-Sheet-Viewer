"""Full backend lifecycle with persistent SQLite and controlled external services."""

import asyncio
import copy
import hashlib
import json
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select

from app.config import Settings
from app.data_service.auth import hash_password
from app.data_service.main import create_data_app
from app.data_service.settings import DataServiceSettings
from app.data_service.worker import Worker
from app.domain.models import DocumentDispatchResponse
from app.main import create_app
from app.persistence.database import create_session_factory, session_scope
from app.persistence.models import (
    AuthSession,
    Base,
    Document,
    IntegrationTask,
    QuestionEmbedding,
    QuestionRecord,
    UploadIntent,
    User,
    utc_now,
)
from app.storage.b2 import B2Settings, B2Storage


class MemoryS3:
    def __init__(self):
        self.objects = {}

    def generate_presigned_url(self, operation, *, Params, ExpiresIn, HttpMethod=None):
        return "https://s3.test/" + Params["Key"]

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        data, mime = self.objects[Key]
        return {
            "ContentLength": len(data),
            "ContentType": mime,
            "ETag": '"' + hashlib.md5(data).hexdigest() + '"',
        }

    def get_object(self, *, Bucket, Key):
        data = self.objects[Key][0]

        class Body:
            def iter_chunks(self, chunk_size):
                yield data

            def close(self):
                pass

        return {"Body": Body()}

    def copy_object(self, *, Bucket, Key, CopySource, CopySourceIfMatch, MetadataDirective):
        assert self.head_object(Bucket=Bucket, Key=CopySource["Key"])["ETag"] == CopySourceIfMatch
        self.objects[Key] = self.objects[CopySource["Key"]]


class Embeddings:
    def embed(self, texts):
        return [[1.0, 0.0, 0.0] for text in texts]


class TeamTransport(httpx.AsyncBaseTransport):
    def __init__(self, data_app):
        self.data = httpx.ASGITransport(app=data_app)
        self.jobs = {}

    async def handle_async_request(self, request):
        if request.url.host == "data.test":
            return await self.data.handle_async_request(request)
        assert request.headers["X-Internal-Token"] == "ai-outbound"
        if request.method == "POST" and request.url.path == "/internal/v1/document-jobs":
            payload = json.loads(request.content)
            key = payload["client_job_key"]
            job = self.jobs.setdefault(
                key,
                {
                    **{k: v for k, v in payload.items() if k != "request_id"},
                    "job_id": "ai-" + str(len(self.jobs) + 1),
                    "status": "queued",
                    "progress": 0,
                },
            )
            return httpx.Response(200, json={"job_id": job["job_id"], "status": "queued"})
        job_id = request.url.path.rsplit("/", 1)[-1]
        job = next((j for j in self.jobs.values() if j["job_id"] == job_id), None)
        return httpx.Response(200 if job else 404, json=job or {"error": "missing"})


@pytest.fixture
def backend(tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "data.db"), connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi, _):
        dbapi.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        for role in ("admin", "reviewer", "uploader"):
            session.add(
                User(
                    name=role,
                    email=role + "@example.edu",
                    role=role,
                    password_hash=hash_password("local-test-password"),
                )
            )
    s3 = MemoryS3()
    storage = B2Storage(B2Settings("https://s3.test", "private", "key", "secret"), client=s3)
    config = DataServiceSettings(
        _env_file=None,
        person2_inbound_token="p2-token",
        ai_data_token="ai-data",
        embedding_dimensions=3,
        embedding_model="test-model",
    )
    data_app = create_data_app(
        config, session_factory=factory, storage=storage, embeddings=Embeddings()
    )
    peer = TeamTransport(data_app)
    upstream = httpx.AsyncClient(transport=peer)
    settings = Settings(
        _env_file=None,
        app_env="testing",
        backend_mode="http",
        person2_base_url="http://data.test",
        ai_base_url="http://ai.test",
        person2_service_token="p2-token",
        ai_service_token="ai-outbound",
        document_dispatch_token="dispatch-token",
        ai_callback_token="callback-token",
        api_key="student-gateway-key",
        capture_required=True,
        rate_limit_per_minute=0,
    )
    with (
        TestClient(data_app) as data,
        TestClient(create_app(settings, http_client=upstream)) as gateway,
    ):

        def dispatch(payload):
            response = gateway.post(
                "/internal/v1/documents/dispatch",
                json=payload,
                headers={"X-Internal-Token": "dispatch-token"},
            )
            assert response.status_code == 200, response.text
            return DocumentDispatchResponse.model_validate(response.json())

        worker = Worker(factory, config, embeddings=Embeddings(), dispatch=dispatch)
        yield SimpleNamespace(
            client=gateway,
            data=data,
            app=data_app,
            factory=factory,
            engine=engine,
            config=config,
            s3=s3,
            worker=worker,
            peer=peer,
            storage=storage,
        )
    asyncio.run(upstream.aclose())
    engine.dispose()


def auth(backend, role="admin"):
    response = backend.client.post(
        "/api/v1/auth/login",
        json={
            "email": role + "@example.edu",
            "password": "local-test-password",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def upload(backend, headers, *, key="document-1", process=True, document_type="tutorial_sheet"):
    content = b"%PDF-1.4 test fixture"
    payload = {
        "filename": "calculus.pdf",
        "content_type": "application/pdf",
        "size_bytes": len(content),
        "client_upload_key": key,
        "sha256": hashlib.sha256(content).hexdigest(),
        "title": "Calculus",
        "subject": "Mathematics",
        "module": "Calculus",
        "document_type": document_type,
        "source_type": "tutorial",
        "year": 2026,
        "process": process,
    }
    response = backend.client.post("/api/v1/admin/uploads", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    intent = response.json()
    source_key = urlsplit(intent["upload_url"]).path.lstrip("/")
    backend.s3.objects[source_key] = (content, "application/pdf")
    confirmed = backend.client.post(
        f"/api/v1/admin/uploads/{intent['id']}/confirm", headers=headers
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json(), payload, source_key


def extraction(backend, headers):
    document, _, _ = upload(backend, headers)
    assert backend.worker.run_once()
    job = next(iter(backend.peer.jobs.values()))
    job.update(status="completed", progress=100, extracted_count=1)
    payload = {
        k: job[k] for k in ("document_id", "document_version", "source_type", "client_job_key")
    }
    payload.update(
        event_id="result-event-1",
        status="completed",
        questions=[
            {
                "extraction_id": "q1",
                "text": "Differentiate x squared",
                "subject": "Mathematics",
                "module": "Calculus",
                "topic": "Differentiation",
                "official_solution": "2x",
                "source": {
                    "document_id": document["document_id"],
                    "source_type": "tutorial",
                    "page_number": 1,
                },
            }
        ],
    )
    response = backend.client.post(
        f"/internal/v1/document-jobs/{job['job_id']}/result",
        headers={"X-Internal-Token": "callback-token"},
        json=payload,
    )
    assert response.status_code == 200, response.text
    questions = backend.client.get("/api/v1/admin/questions", headers=headers).json()["items"]
    assert len(questions) == 1
    return document["document_id"], questions[0], payload, job


def approve(backend, headers, question):
    response = backend.client.post(
        f"/api/v1/admin/questions/{question['id']}/review",
        headers=headers,
        json={
            "expected_revision": question["revision"],
            "status": "approved",
            "approve_solution": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def publish(backend, headers, document_id, visibility="public"):
    return backend.client.post(
        f"/api/v1/admin/documents/{document_id}/publication",
        headers=headers,
        json={"visibility": visibility},
    )


def search(backend, path="search", **data):
    return backend.client.post(
        "/api/v1/" + path,
        headers={"X-API-Key": "student-gateway-key"},
        json={"query": "differentiate", **data},
    )


def test_complete_flow_persistence_and_unchanged_search_contract(backend):
    headers = auth(backend)
    doc, question, _, _ = extraction(backend, headers)
    assert search(backend).json()["items"] == []
    assert publish(backend, headers, doc).status_code == 409
    question = approve(backend, headers, question)
    assert search(backend).json()["items"] == []  # still a private document
    assert publish(backend, headers, doc).status_code == 200
    result = search(backend).json()
    assert set(result) == {"items", "total", "captured", "request_id"}
    assert result["captured"] is True
    assert result["items"][0]["question"]["official_solution"] == "2x"
    assert search(backend, "search/semantic").json()["items"] == []
    assert backend.worker.run_once()
    semantic = search(backend, "search/semantic").json()
    assert semantic["items"][0]["question"]["id"] == question["id"]
    assert search(backend, "search/semantic", filters={"subject": "Physics"}).json()["items"] == []
    # New application instance and sessions still read durable review/auth/index state.
    with TestClient(
        create_data_app(
            backend.config,
            session_factory=backend.factory,
            storage=backend.storage,
            embeddings=Embeddings(),
        )
    ) as restarted:
        assert restarted.get("/api/v1/auth/me", headers=headers).status_code == 200
        found = restarted.post(
            "/internal/v1/search/semantic",
            headers={"X-Internal-Token": "p2-token"},
            json={"query": "differentiate"},
        )
        assert found.json()["items"][0]["question"]["id"] == question["id"]
    assert publish(backend, headers, doc, "private").status_code == 200
    assert search(backend).json()["items"] == []
    assert search(backend, "search/semantic").json()["items"] == []


def test_review_edit_conflict_reindex_and_replayed_callback_preserves_edits(backend):
    headers = auth(backend)
    doc, question, payload, job = extraction(backend, headers)
    question = approve(backend, headers, question)
    publish(backend, headers, doc)
    assert backend.worker.run_once()
    edit = {
        "expected_revision": question["revision"],
        "text": "Differentiate x cubed",
        "official_solution": "3x squared",
    }
    route = f"/api/v1/admin/questions/{question['id']}"
    changed = backend.client.patch(route, headers=headers, json=edit)
    assert changed.status_code == 200, changed.text
    assert changed.json()["status"] == "pending_review"
    assert backend.client.patch(route, headers=headers, json=edit).status_code == 409
    assert search(backend, "search/semantic").json()["items"] == []
    replay = copy.deepcopy(payload)
    replay["event_id"] = "another-result-event"
    callback = backend.client.post(
        f"/internal/v1/document-jobs/{job['job_id']}/result",
        headers={"X-Internal-Token": "callback-token"},
        json=replay,
    )
    assert callback.status_code == 200, callback.text
    preserved = backend.client.get(route, headers=headers).json()
    assert preserved["text"] == "Differentiate x cubed"
    assert preserved["official_solution"] == "3x squared"
    approve(backend, headers, preserved)
    assert backend.worker.run_once()
    assert (
        search(backend, "search/semantic").json()["items"][0]["question"]["text"]
        == "Differentiate x cubed"
    )
    with backend.factory() as session:
        assert session.scalar(select(func.count()).select_from(QuestionRecord)) == 1


def test_auth_roles_expiry_revocation_and_service_tokens_are_not_logins(backend):
    assert (
        backend.client.get(
            "/api/v1/admin/documents", headers={"X-API-Key": "student-gateway-key"}
        ).status_code
        == 401
    )
    assert (
        backend.client.get(
            "/api/v1/admin/documents", headers={"X-Internal-Token": "p2-token"}
        ).status_code
        == 401
    )
    headers = auth(backend, "uploader")
    assert backend.client.get("/api/v1/admin/users", headers=headers).status_code == 403
    doc, _, _ = upload(backend, headers, process=False)
    assert publish(backend, headers, doc["document_id"]).status_code == 403
    assert backend.client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert backend.client.get("/api/v1/auth/me", headers=headers).status_code == 401
    headers = auth(backend)
    with session_scope(backend.factory) as session:
        for token in session.scalars(select(AuthSession)):
            token.expires_at = utc_now() - timedelta(seconds=1)
    assert backend.client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_uploads_are_idempotent_verified_and_sealed(backend):
    headers = auth(backend)
    confirmed, payload, source = upload(backend, headers)
    replay = backend.client.post("/api/v1/admin/uploads", headers=headers, json=payload)
    assert replay.status_code == 201
    assert replay.json() == confirmed
    confirmation = backend.client.post(
        f"/api/v1/admin/uploads/{confirmed['id']}/confirm", headers=headers
    )
    assert confirmation.json() == confirmed
    changed = backend.client.post(
        "/api/v1/admin/uploads", headers=headers, json={**payload, "title": "Changed"}
    )
    assert changed.status_code == 409
    with backend.factory() as session:
        document = session.scalar(select(Document))
        assert document.object_key != source
        backend.s3.objects[source] = (b"overwritten", "application/pdf")
        assert backend.s3.objects[document.object_key][0].startswith(b"%PDF")
        assert session.scalar(select(func.count()).select_from(IntegrationTask)) == 1
    other = auth(backend, "uploader")
    assert (
        backend.client.post(
            f"/api/v1/admin/uploads/{confirmed['id']}/confirm", headers=other
        ).status_code
        == 403
    )


def test_missing_wrong_size_checksum_and_expired_uploads_fail_without_document(backend):
    headers = auth(backend)
    payload = {
        "filename": "paper.pdf",
        "content_type": "application/pdf",
        "size_bytes": 3,
        "client_upload_key": "bad-upload-1",
        "sha256": "0" * 64,
        "title": "Paper",
        "subject": "Math",
        "document_type": "question_paper",
        "source_type": "pyq",
    }
    response = backend.client.post("/api/v1/admin/uploads", headers=headers, json=payload)
    intent = response.json()
    route = f"/api/v1/admin/uploads/{intent['id']}/confirm"
    assert backend.client.post(route, headers=headers).status_code == 502
    backend.s3.objects[urlsplit(intent["upload_url"]).path.lstrip("/")] = (
        b"abc",
        "application/pdf",
    )
    assert backend.client.post(route, headers=headers).status_code == 502
    with session_scope(backend.factory) as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 0
        session.scalar(select(UploadIntent)).expires_at = utc_now() - timedelta(seconds=1)
    assert backend.client.post(route, headers=headers).status_code == 410


def test_worker_retries_restart_and_fences_stale_lease(backend):
    headers = auth(backend)
    upload(backend, headers)
    broken = Worker(
        backend.factory,
        backend.config,
        dispatch=lambda _: (_ for _ in ()).throw(RuntimeError("secret")),
    )
    assert broken.run_once()
    with session_scope(backend.factory) as session:
        task = session.scalar(select(IntegrationTask))
        assert task.status == "queued" and task.attempts == 1
        assert task.last_error == "WORKER_OPERATION_FAILED"
        task.next_attempt_at = utc_now() - timedelta(seconds=1)
    claimed = broken._claim()
    with session_scope(backend.factory) as session:
        task = session.get(IntegrationTask, claimed[0])
        task.lease_until = utc_now() - timedelta(seconds=1)
    assert backend.worker.run_once()
    broken._failed(claimed[0], claimed[1], "STALE_WORKER")
    with backend.factory() as session:
        task = session.get(IntegrationTask, claimed[0])
        assert task.status == "succeeded" and task.attempts == 3


def test_late_embedding_cannot_restore_unreviewed_content(backend):
    headers = auth(backend)
    doc, question, _, _ = extraction(backend, headers)
    question = approve(backend, headers, question)
    publish(backend, headers, doc)

    class RacingEmbeddings:
        def embed(self, texts):
            response = backend.client.patch(
                f"/api/v1/admin/questions/{question['id']}",
                headers=headers,
                json={"expected_revision": question["revision"], "text": "Changed while indexing"},
            )
            assert response.status_code == 200
            return [[1, 0, 0]]

    worker = Worker(backend.factory, backend.config, embeddings=RacingEmbeddings())
    assert worker.run_once()
    with backend.factory() as session:
        assert session.scalar(select(func.count()).select_from(QuestionEmbedding)) == 0
    assert search(backend, "search/semantic").json()["items"] == []


def test_solution_assets_and_ai_credential_are_scoped(backend):
    headers = auth(backend)
    doc, question, _, _ = extraction(backend, headers)
    answer_doc, _, _ = upload(
        backend, headers, key="answer-sheet-1", process=False, document_type="answer_sheet"
    )
    data = {
        "filename": "solution.png",
        "content_type": "image/png",
        "size_bytes": 8,
        "client_upload_key": "solution-asset-1",
        "document_id": answer_doc["document_id"],
        "document_version": "v1",
        "kind": "solution_image",
    }
    url = "/internal/v1/ingestion/assets/uploads"
    assert (
        backend.data.post(url, json=data, headers={"X-Internal-Token": "p2-token"}).status_code
        == 401
    )
    response = backend.data.post(url, json=data, headers={"X-Internal-Token": "ai-data"})
    assert response.status_code == 201, response.text
    intent = response.json()
    backend.s3.objects[urlsplit(intent["upload_url"]).path.lstrip("/")] = (
        b"\x89PNG\r\n\x1a\n",
        "image/png",
    )
    response = backend.data.post(
        url + f"/{intent['id']}/confirm", headers={"X-Internal-Token": "ai-data"}
    )
    assert response.status_code == 200, response.text
    asset_id = response.json()["asset_id"]
    route = f"/api/v1/admin/questions/{question['id']}"
    invalid = backend.client.patch(
        route, headers=headers, json={"expected_revision": 1, "solution_asset_id": asset_id}
    )
    assert invalid.status_code == 409
    updated = backend.client.patch(
        route,
        headers=headers,
        json={
            "expected_revision": 1,
            "solution_asset_id": asset_id,
            "solution_document_id": answer_doc["document_id"],
        },
    )
    assert updated.status_code == 200, updated.text
    approve(backend, headers, updated.json())
    assert publish(backend, headers, doc).status_code == 200
    links = backend.client.get(
        f"/api/v1/questions/{question['id']}/assets", headers={"X-API-Key": "student-gateway-key"}
    )
    assert links.status_code == 200, links.text
    assert links.json()["solution_image_url"].startswith("https://s3.test/documents/")
    assert links.json()["solution_document_id"] == answer_doc["document_id"]


def test_invalid_admin_payloads_use_safe_error_envelope_and_proxy_schema(backend):
    response = backend.client.post("/api/v1/auth/login", json={"password": "NEVER_ECHO_ME"})
    assert response.status_code == 422
    assert "NEVER_ECHO_ME" not in response.text
    paths = backend.client.get("/openapi.json").json()["paths"]
    schema = paths["/api/v1/admin/questions/{question_id}"]["patch"]
    assert "requestBody" in schema
    assert {p["name"] for p in schema["parameters"]} == {"question_id"}


def test_role_changes_revoke_sessions_and_passwords_are_not_trimmed(backend):
    admin = auth(backend)
    password = "  trailing-and-leading-spaces  "
    created = backend.client.post(
        "/api/v1/admin/users",
        headers=admin,
        json={
            "name": "New reviewer",
            "email": "new@example.edu",
            "role": "reviewer",
            "password": password,
        },
    )
    assert created.status_code == 201, created.text
    assert "password" not in created.text
    bad = backend.client.post(
        "/api/v1/auth/login", json={"email": "new@example.edu", "password": password.strip()}
    )
    assert bad.status_code == 401
    signed = backend.client.post(
        "/api/v1/auth/login", json={"email": "new@example.edu", "password": password}
    )
    assert signed.status_code == 200
    token = {"Authorization": "Bearer " + signed.json()["access_token"]}
    changed = backend.client.patch(
        "/api/v1/admin/users/" + created.json()["id"], headers=admin, json={"is_active": False}
    )
    assert changed.status_code == 200
    assert backend.client.get("/api/v1/auth/me", headers=token).status_code == 401


def test_failed_commit_never_returns_a_successful_login(backend):
    from sqlalchemy.orm import Session

    def reject_commit(session):
        raise RuntimeError("simulated database commit failure")

    event.listen(Session, "before_commit", reject_commit)
    try:
        response = backend.client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.edu", "password": "local-test-password"},
        )
        assert response.status_code == 500
        assert "access_token" not in response.text
    finally:
        event.remove(Session, "before_commit", reject_commit)
    with backend.factory() as session:
        assert session.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_exhausted_dispatch_task_can_be_retried_without_new_ai_identity(backend):
    headers = auth(backend)
    confirmed, _, _ = upload(backend, headers)
    config = backend.config.model_copy(update={"worker_max_attempts": 1})
    broken = Worker(
        backend.factory, config, dispatch=lambda _: (_ for _ in ()).throw(RuntimeError())
    )
    assert broken.run_once()
    with backend.factory() as session:
        task = session.scalar(select(IntegrationTask))
        assert task.status == "failed"
        task_id = str(task.id)
    rejected = backend.client.post(
        f"/api/v1/admin/documents/{confirmed['document_id']}/process",
        headers=headers,
        json={
            "document_id": confirmed["document_id"],
            "document_version": "v1",
            "source_type": "tutorial",
            "client_job_key": "new-key-incorrect",
        },
    )
    assert rejected.status_code == 409
    retry = backend.client.post(f"/api/v1/admin/tasks/{task_id}/retry", headers=headers)
    assert retry.status_code == 200
    assert backend.worker.run_once()
    assert len(backend.peer.jobs) == 1


def test_unapproved_solutions_and_archived_questions_do_not_leak(backend):
    headers = auth(backend)
    doc, question, _, _ = extraction(backend, headers)
    response = backend.client.post(
        f"/api/v1/admin/questions/{question['id']}/review",
        headers=headers,
        json={"expected_revision": 1, "status": "approved"},
    )
    assert response.status_code == 200
    publish(backend, headers, doc)
    assert search(backend).json()["items"][0]["question"]["official_solution"] is None
    archived = backend.client.post(
        f"/api/v1/admin/questions/{question['id']}/review",
        headers=headers,
        json={"expected_revision": 2, "status": "archived"},
    )
    assert archived.status_code == 200
    assert backend.worker.run_once()  # the old indexing task is now obsolete
    assert search(backend).json()["items"] == []
    assert search(backend, "search/semantic").json()["items"] == []
