import hashlib
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from app.data_service.main import create_data_app
from app.data_service.settings import DataServiceSettings
from app.domain.models import DocumentResultEvent
from app.persistence.database import create_session_factory
from app.persistence.models import (
    Answer,
    Base,
    Document,
    DocumentProcessingJob,
    DocumentResultReceipt,
    QueryEventRecord,
    QuestionRecord,
)
from app.storage.b2 import B2Settings, B2Storage

TOKEN = "person2-inbound-test-token"


def make_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    settings = DataServiceSettings(_env_file=None, person2_inbound_token=SecretStr(TOKEN))
    app = create_data_app(settings, session_factory=factory)
    return TestClient(app), factory, engine


def make_storage_client():
    client, factory, engine = make_client()
    storage = B2Storage(
        B2Settings(
            endpoint_url="https://s3.example",
            bucket_name="private-bucket",
            access_key_id="test-key",
            secret_access_key="test-secret",
            delivery_base_url="https://worker.example",
        ),
        client=UploadClient(),
    )
    client.app.state.data_service.storage = storage
    return client, factory, engine


class UploadClient:
    def __init__(self):
        self.deleted = None
        self.contents = b"x" * 128

    def generate_presigned_url(self, operation, *, Params, ExpiresIn, HttpMethod=None):
        return "https://s3.example/signed"

    def head_object(self, *, Bucket, Key):
        return {
            "ContentLength": len(self.contents),
            "ContentType": "application/pdf",
            "ETag": '"etag"',
        }

    def get_object(self, *, Bucket, Key):
        contents = self.contents

        class Body:
            def iter_chunks(self, chunk_size):
                yield contents

            def close(self):
                pass

        return {"Body": Body()}

    def delete_object(self, *, Bucket, Key):
        self.deleted = (Bucket, Key)


def add_document(factory, *, document_id="doc-1", version="v1", source_type="tutorial"):
    with factory() as session:
        document = Document(
            external_id=document_id,
            current_version=version,
            title="Calculus notes",
            document_type="tutorial_sheet",
            source_type=source_type,
            original_filename="calculus.pdf",
            object_key=f"documents/{uuid4()}/calculus.pdf",
            bucket_name="test-private",
            mime_type="application/pdf",
            file_size_bytes=1024,
            publication_year=2024,
            visibility="public",
        )
        session.add(document)
        session.commit()


def result_payload(**overrides):
    payload = {
        "document_id": "doc-1",
        "document_version": "v1",
        "source_type": "tutorial",
        "client_job_key": "doc-1-v1-extract",
        "event_id": "result-job-1-v1",
        "job_id": "ai-job-1",
        "request_id": "p2-test-request",
        "status": "completed",
        "questions": [
            {
                "extraction_id": "page2-q4a",
                "text": "Differentiate x cubed using the power rule",
                "subject": "Engineering Mathematics",
                "module": "Calculus",
                "topic": "Differentiation",
                "source": {
                    "source_type": "tutorial",
                    "document_id": "doc-1",
                    "document_title": "Calculus notes",
                    "page_number": 2,
                    "question_number": "4a",
                    "year": 2024,
                },
                "official_solution": "3x squared",
                "confidence": 0.98,
                "needs_review": True,
            }
        ],
    }
    payload.update(overrides)
    return payload


def internal_headers():
    return {"X-Internal-Token": TOKEN, "X-Request-ID": "p2-test-request"}


def test_data_service_requires_token_and_health_checks_database():
    client, _, engine = make_client()
    with client:
        assert client.get("/health/ready").status_code == 401
        response = client.get("/health/ready", headers=internal_headers())
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}
        assert (
            client.get("/internal/v1/catalog", headers={"X-Internal-Token": "wrong"}).status_code
            == 401
        )
    engine.dispose()


def test_upload_lifecycle_authorizes_confirms_downloads_and_deletes_private_document():
    client, factory, engine = make_storage_client()
    headers = internal_headers()
    with client:
        authorized = client.post(
            "/internal/v1/documents/uploads",
            headers=headers,
            json={
                "external_id": "upload-doc",
                "title": "Upload document",
                "document_type": "tutorial_sheet",
                "source_type": "tutorial",
                "original_filename": "paper.pdf",
                "mime_type": "application/pdf",
                "file_size_bytes": 128,
                "publication_year": 2024,
            },
        )
        assert authorized.status_code == 200, authorized.text
        assert authorized.json()["upload_url"] == "https://s3.example/signed"
        assert authorized.json()["document_version"] == "v1"

        confirmed = client.post(
            "/internal/v1/documents/upload-doc/uploads/confirm",
            headers=headers,
            json={
                "document_id": "upload-doc",
                "document_version": "v1",
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "succeeded"
        assert confirmed.json()["sha256"] == hashlib.sha256(b"x" * 128).hexdigest()

        downloaded = client.get("/internal/v1/documents/upload-doc/download", headers=headers)
        assert downloaded.status_code == 200
        assert downloaded.json()["expires_in_seconds"] == 900

        deleted = client.delete("/internal/v1/documents/upload-doc", headers=headers)
        assert deleted.status_code == 200
        assert deleted.json() == {"document_id": "upload-doc", "deleted": True}
        with factory() as session:
            assert (
                session.scalar(select(Document).where(Document.external_id == "upload-doc")) is None
            )
    engine.dispose()


def test_content_endpoint_retrieves_public_file_from_delivery_worker(monkeypatch):
    client, factory, engine = make_storage_client()
    add_document(factory)
    with factory() as session:
        object_key = session.scalar(select(Document).where(Document.external_id == "doc-1")).object_key

    class WorkerClient:
        def __init__(self, **kwargs):
            self.closed = False

        def build_request(self, method, url):
            return httpx.Request(method, url)

        def send(self, request, *, stream):
            assert request.url == httpx.URL(f"https://worker.example/{object_key}")
            return httpx.Response(
                200,
                headers={"content-type": "application/pdf", "etag": "worker-etag"},
                content=b"%PDF-worker",
                request=request,
            )

        def close(self):
            self.closed = True

    monkeypatch.setattr("app.data_service.api.httpx.Client", WorkerClient)
    with client:
        response = client.get("/internal/v1/documents/doc-1/content", headers=internal_headers())
        assert response.status_code == 200
        assert response.content == b"%PDF-worker"
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["etag"] == "worker-etag"
    engine.dispose()


def test_content_endpoint_rejects_private_signed_downloads():
    client, factory, engine = make_storage_client()
    add_document(factory)
    with factory() as session:
        session.scalar(select(Document).where(Document.external_id == "doc-1")).visibility = (
            "private"
        )
        session.commit()
    with client:
        response = client.get("/internal/v1/documents/doc-1/content", headers=internal_headers())
        assert response.status_code == 403
    engine.dispose()


def test_document_result_is_transactional_review_gated_and_replay_safe():
    client, factory, engine = make_client()
    add_document(factory)
    headers = internal_headers()
    with client:
        response = client.post(
            "/internal/v1/document-results", headers=headers, json=result_payload()
        )
        assert response.status_code == 200, response.text
        ack = response.json()
        assert ack["accepted"] is True
        assert ack["indexing_status"] == "pending"

        replay = result_payload()
        replay["request_id"] = "a-retry-request-id"
        replayed = client.post("/internal/v1/document-results", headers=headers, json=replay)
        assert replayed.status_code == 200
        assert replayed.json() == ack

        new_event_id_retry = result_payload(event_id="result-job-1-v1-retry")
        accepted_again = client.post(
            "/internal/v1/document-results",
            headers=headers,
            json=new_event_id_retry,
        )
        assert accepted_again.status_code == 200

        conflicting = result_payload()
        conflicting["questions"][0]["text"] = "Changed after acceptance"
        conflict = client.post("/internal/v1/document-results", headers=headers, json=conflicting)
        assert conflict.status_code == 409

        with factory() as session:
            question = session.scalar(select(QuestionRecord))
            assert question is not None
            assert question.status == "pending_review"
            assert question.document_version == "v1"
            assert question.page_start == 2
            assert session.scalar(select(func.count()).select_from(QuestionRecord)) == 1
            answer = session.scalar(select(Answer))
            assert answer is not None
            assert answer.review_status == "pending_review"
            assert session.scalar(select(func.count()).select_from(DocumentProcessingJob)) == 1
            assert session.scalar(select(func.count()).select_from(DocumentResultReceipt)) == 2
    engine.dispose()


def test_old_document_version_is_rejected_and_failure_ack_is_not_applicable():
    client, factory, engine = make_client()
    add_document(factory, version="v2")
    headers = internal_headers()
    with client:
        stale = client.post(
            "/internal/v1/document-results",
            headers=headers,
            json=result_payload(event_id="stale-result-event"),
        )
        assert stale.status_code == 409
        failure = result_payload(
            event_id="failed-result-event",
            document_version="v2",
            status="failed",
            questions=[],
            error={"code": "NO_QUESTIONS_FOUND", "message": "No questions were extracted"},
        )
        response = client.post("/internal/v1/document-results", headers=headers, json=failure)
        assert response.status_code == 200, response.text
        assert response.json()["indexing_status"] == "not_applicable"
    engine.dispose()


def test_public_contract_routes_return_only_approved_content_and_capture_events():
    client, factory, engine = make_client()
    add_document(factory)
    headers = internal_headers()
    with client:
        client.post("/internal/v1/document-results", headers=headers, json=result_payload())
        pending_search = client.post(
            "/internal/v1/search",
            headers=headers,
            json={"query": "differentiate power rule", "limit": 5},
        )
        assert pending_search.status_code == 200
        assert pending_search.json()["items"] == []
        with factory() as session:
            question = session.scalar(select(QuestionRecord))
            assert question is not None
            question.status = "approved"
            session.scalar(select(Answer)).review_status = "approved"
            session.commit()

        response = client.post(
            "/internal/v1/search",
            headers=headers,
            json={
                "query": "differentiate power rule",
                "filters": {
                    "subject": "engineering mathematics",
                    "module": "calculus",
                    "topic": "differentiation",
                    "year": 2024,
                    "source_type": "tutorial",
                },
                "limit": 5,
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["question"]["source"]["page_number"] == 2
        assert item["question"]["source"]["year"] == 2024
        assert item["question"]["official_solution"] == "3x squared"

        detail = client.get(f"/internal/v1/questions/{item['question']['id']}", headers=headers)
        assert detail.status_code == 200
        similar = client.get(
            f"/internal/v1/questions/{item['question']['id']}/similar",
            headers=headers,
        )
        assert similar.status_code == 200
        assert similar.json()["items"] == []
        catalog = client.get("/internal/v1/catalog", headers=headers)
        assert catalog.status_code == 200
        assert catalog.json()["combinations"][0]["subject"] == "Engineering Mathematics"

        event = {
            "event_id": "query-event-1",
            "timestamp": "2026-10-23T12:00:00Z",
            "event_type": "search",
            "request_id": "capture-request",
            "query": "differentiate",
            "filters": {"subject": "Engineering Mathematics"},
            "result_count": None,
        }
        captured = client.post("/internal/v1/query-events", headers=headers, json=event)
        assert captured.status_code == 200
        assert captured.json()["accepted"] is True
        replay = client.post("/internal/v1/query-events", headers=headers, json=event)
        assert replay.status_code == 200
        new_trace = {**event, "request_id": "different-trace-id"}
        assert (
            client.post("/internal/v1/query-events", headers=headers, json=new_trace).status_code
            == 200
        )
        changed = {**event, "query": "different question"}
        assert (
            client.post("/internal/v1/query-events", headers=headers, json=changed).status_code
            == 409
        )

        with factory() as session:
            assert session.scalar(select(func.count()).select_from(QueryEventRecord)) == 1
    engine.dispose()


def test_document_result_input_is_validated_before_database_work():
    DocumentResultEvent.model_validate(result_payload())
