"""Database-backed outbox worker. Run with python -m app.data_service.worker."""

import argparse
import logging
import secrets
import time
from datetime import timedelta

import httpx
from sqlalchemy import and_, func, or_, select

from app.core.errors import ServiceError
from app.data_service.semantic import LocalEmbeddings, embedding_text, normalize
from app.data_service.settings import DataServiceSettings
from app.domain.models import DocumentDispatchResponse
from app.persistence.database import create_database_engine, create_session_factory, session_scope
from app.persistence.models import (
    Document,
    DocumentProcessingJob,
    IntegrationTask,
    QuestionEmbedding,
    QuestionRecord,
    utc_now,
)

log = logging.getLogger("mathclub.worker")


class Worker:
    def __init__(self, factory, settings, *, embeddings=None, dispatch=None):
        self.factory, self.settings = factory, settings
        self.embeddings = embeddings or LocalEmbeddings(settings)
        self.dispatch = dispatch or self._dispatch_http

    def _claim(self):
        with session_scope(self.factory) as session:
            now = utc_now()
            task = session.scalar(
                select(IntegrationTask)
                .where(
                    or_(
                        and_(
                            IntegrationTask.status == "queued",
                            IntegrationTask.next_attempt_at <= now,
                        ),
                        and_(
                            IntegrationTask.status == "running", IntegrationTask.lease_until <= now
                        ),
                    )
                )
                .order_by(IntegrationTask.next_attempt_at, IntegrationTask.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if task is None:
                return None
            task.status = "running"
            task.attempts += 1
            task.lease_token = secrets.token_hex(24)
            task.lease_until = now + timedelta(seconds=self.settings.worker_lease_seconds)
            return task.id, task.lease_token, task.kind, dict(task.payload), task.attempts

    @staticmethod
    def _owned(session, task_id, lease):
        task = session.scalar(
            select(IntegrationTask)
            .where(
                IntegrationTask.id == task_id,
                IntegrationTask.status == "running",
                IntegrationTask.lease_token == lease,
                IntegrationTask.lease_until > utc_now(),
            )
            .with_for_update()
        )
        return task

    @staticmethod
    def _finish(task):
        task.status, task.last_error = "succeeded", None
        task.lease_until, task.lease_token = None, None

    def _dispatch_http(self, payload):
        if not self.settings.document_dispatch_token:
            raise ServiceError(
                "DISPATCH_NOT_CONFIGURED", "Configure the document dispatch token", 503
            )
        try:
            with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
                with client.stream(
                    "POST",
                    self.settings.person1_base_url.rstrip("/") + "/internal/v1/documents/dispatch",
                    json=payload,
                    headers={
                        "X-Internal-Token": self.settings.document_dispatch_token.get_secret_value()
                    },
                ) as response:
                    if response.status_code != 200:
                        raise ServiceError(
                            "DISPATCH_FAILED", "Document dispatcher did not accept the job", 503
                        )
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 65536:
                            raise ServiceError(
                                "DISPATCH_FAILED", "Dispatch response is too large", 502
                            )
                    try:
                        return DocumentDispatchResponse.model_validate_json(body)
                    except ValueError as exc:
                        raise ServiceError(
                            "DISPATCH_FAILED", "Dispatch acknowledgement is invalid", 502
                        ) from exc
        except httpx.RequestError as exc:
            raise ServiceError(
                "DISPATCH_FAILED", "Document dispatcher is unreachable", 503
            ) from exc

    def _process_dispatch(self, task_id, lease, payload):
        with session_scope(self.factory) as session:
            document = session.scalar(
                select(Document).where(Document.external_id == payload["document_id"])
            )
            if document is None or document.current_version != payload["document_version"]:
                raise ServiceError(
                    "DOCUMENT_VERSION_CONFLICT", "Queued document version is no longer current", 409
                )
        ack = self.dispatch(payload)
        if ack.document_id != payload["document_id"]:
            raise ServiceError(
                "DISPATCH_FAILED", "Dispatch acknowledgement has the wrong document", 502
            )
        with session_scope(self.factory) as session:
            task = self._owned(session, task_id, lease)
            if task is None:
                return
            # Match callback lock order: document, then its processing job.
            session.scalar(
                select(Document)
                .where(
                    Document.external_id == payload["document_id"],
                )
                .with_for_update()
            )
            job = session.scalar(
                select(DocumentProcessingJob)
                .where(
                    DocumentProcessingJob.client_job_key == payload["client_job_key"],
                )
                .with_for_update()
            )
            if job is None or job.ai_job_id not in {None, ack.job_id}:
                raise ServiceError(
                    "JOB_IDENTITY_CONFLICT", "AI changed the job ID for the same client key", 409
                )
            job.ai_job_id, job.attempts = ack.job_id, task.attempts
            # A fast callback may already have committed a terminal result.
            if job.result_sha256 is None:
                job.status, job.started_at, job.error_message = "running", utc_now(), None
                job.document.processing_status = "processing"
            self._finish(task)

    def _process_index(self, task_id, lease, payload):
        if payload["model"] != self.settings.embedding_model:
            raise ServiceError("EMBEDDING_MODEL_CHANGED", "Reindex using the configured model", 409)
        vector = None
        with session_scope(self.factory) as session:
            question = session.scalar(
                select(QuestionRecord).where(QuestionRecord.external_id == payload["question_id"])
            )
            current = (
                question is not None
                and question.status == "approved"
                and question.revision == payload["revision"]
            )
            text = embedding_text(session, question) if current else None
        if text is not None:
            vector = normalize(self.embeddings.embed([text])[0], self.settings.embedding_dimensions)
        with session_scope(self.factory) as session:
            task = self._owned(session, task_id, lease)
            if task is None:
                return
            question = session.scalar(
                select(QuestionRecord)
                .where(
                    QuestionRecord.external_id == payload["question_id"],
                )
                .with_for_update()
            )
            if (
                vector is not None
                and question is not None
                and question.status == "approved"
                and question.revision == payload["revision"]
            ):
                record = session.get(QuestionEmbedding, question.id)
                if record is None:
                    record = QuestionEmbedding(question_id=question.id)
                    session.add(record)
                record.embedding, record.model_name = vector, payload["model"]
                record.content_revision = question.revision
                session.flush()
                pending = session.scalar(
                    select(func.count())
                    .select_from(QuestionRecord)
                    .outerjoin(
                        QuestionEmbedding,
                        and_(
                            QuestionEmbedding.question_id == QuestionRecord.id,
                            QuestionEmbedding.content_revision == QuestionRecord.revision,
                            QuestionEmbedding.model_name == payload["model"],
                        ),
                    )
                    .where(
                        QuestionRecord.document_id == question.document_id,
                        QuestionRecord.status == "approved",
                        QuestionEmbedding.question_id.is_(None),
                    )
                )
                question.document.indexing_status = "queued" if pending else "indexed"
            self._finish(task)

    def _failed(self, task_id, lease, code):
        with session_scope(self.factory) as session:
            task = self._owned(session, task_id, lease)
            if task is None:
                return
            task.last_error = code
            terminal = task.attempts >= self.settings.worker_max_attempts
            task.status = "failed" if terminal else "queued"
            task.next_attempt_at = utc_now() + timedelta(
                seconds=min(300, 2 ** min(task.attempts, 8))
            )
            task.lease_until, task.lease_token = None, None
            if terminal and task.kind == "dispatch":
                session.scalar(
                    select(Document)
                    .where(
                        Document.external_id == task.payload["document_id"],
                    )
                    .with_for_update()
                )
                job = session.scalar(
                    select(DocumentProcessingJob)
                    .where(
                        DocumentProcessingJob.client_job_key == task.payload["client_job_key"],
                    )
                    .with_for_update()
                )
                if job and job.result_sha256 is None:
                    job.status, job.error_message, job.attempts = "failed", code, task.attempts
                    job.document.processing_status = "failed"
            elif terminal and task.kind == "index":
                question = session.scalar(
                    select(QuestionRecord)
                    .where(
                        QuestionRecord.external_id == task.payload["question_id"],
                    )
                    .with_for_update()
                )
                if (
                    question
                    and question.status == "approved"
                    and question.revision == task.payload["revision"]
                ):
                    question.document.indexing_status = "failed"

    def run_once(self):
        claimed = self._claim()
        if claimed is None:
            return False
        task_id, lease, kind, payload, attempts = claimed
        try:
            if attempts > self.settings.worker_max_attempts:
                raise ServiceError(
                    "WORKER_RESTART_LIMIT", "Repeated worker restarts exhausted attempts", 503
                )
            if kind == "dispatch":
                self._process_dispatch(task_id, lease, payload)
            else:
                self._process_index(task_id, lease, payload)
        except Exception as exc:
            # Never persist credentials, query bodies, signed URLs or exception reprs.
            code = exc.code if isinstance(exc, ServiceError) else "WORKER_OPERATION_FAILED"
            self._failed(task_id, lease, code)
            log.warning("task=%s error=%s", task_id, code)
        return True


def main():
    parser = argparse.ArgumentParser(description="Process MathClub extraction and indexing outbox")
    parser.add_argument("--once", action="store_true", help="Process at most one due task")
    args = parser.parse_args()
    settings = DataServiceSettings()
    engine = create_database_engine(settings.database_url())
    worker = Worker(create_session_factory(engine), settings)
    logging.basicConfig(level=logging.INFO)
    try:
        while True:
            worked = worker.run_once()
            if args.once:
                break
            if not worked:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
