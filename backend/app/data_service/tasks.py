"""Transactional outbox entries; network calls run only in the separate worker."""

from hashlib import sha256

from sqlalchemy import select

from app.core.errors import ServiceError
from app.data_service.service import _lock_idempotency_key
from app.persistence.models import DocumentProcessingJob, IntegrationTask, QuestionEmbedding


def enqueue(session, kind, key, payload):
    _lock_idempotency_key(session, "task:" + key)
    task = session.scalar(select(IntegrationTask).where(IntegrationTask.dedupe_key == key))
    if task is not None:
        if task.payload != payload:
            raise ServiceError("JOB_KEY_CONFLICT", "Job key was reused with different data", 409)
        return task
    task = IntegrationTask(kind=kind, dedupe_key=key, payload=payload)
    session.add(task)
    session.flush()
    return task


def queue_dispatch(session, document, client_key):
    if document.document_type == "answer_sheet":
        raise ServiceError(
            "SOLUTION_MAPPING_REQUIRED",
            "Upload solution crops and explicitly map them to questions through review",
            409,
        )
    payload = {
        "document_id": document.external_id,
        "document_version": document.current_version,
        "source_type": document.source_type,
        "client_job_key": client_key,
    }
    key = "dispatch:" + client_key
    existing = session.scalar(select(IntegrationTask).where(IntegrationTask.dedupe_key == key))
    if existing is not None:
        return enqueue(session, "dispatch", key, payload)
    if document.processing_status in {"processing", "succeeded"}:
        raise ServiceError("DOCUMENT_ALREADY_PROCESSED", "Document is processing or completed", 409)
    unresolved = session.scalar(
        select(DocumentProcessingJob.id)
        .where(
            DocumentProcessingJob.document_id == document.id,
            DocumentProcessingJob.document_version == document.current_version,
            DocumentProcessingJob.result_sha256.is_(None),
        )
        .limit(1)
    )
    if unresolved is not None:
        raise ServiceError(
            "RETRY_EXISTING_TASK",
            "Retry the existing dispatch task to preserve its AI job identity",
            409,
        )
    task = enqueue(session, "dispatch", key, payload)
    job = session.scalar(
        select(DocumentProcessingJob).where(DocumentProcessingJob.client_job_key == client_key)
    )
    if job is not None:
        raise ServiceError("JOB_KEY_CONFLICT", "Processing key is already in use", 409)
    session.add(
        DocumentProcessingJob(
            document_id=document.id,
            document_version=document.current_version,
            source_type=document.source_type,
            job_type="extraction",
            client_job_key=client_key,
            status="queued",
            attempts=0,
        )
    )
    document.processing_status = "processing"
    return task


def invalidate_index(session, question):
    embedding = session.get(QuestionEmbedding, question.id)
    if embedding is not None:
        session.delete(embedding)
    question.document.indexing_status = "pending"


def queue_index(session, question, model):
    model_key = sha256(model.encode()).hexdigest()[:24]
    task = enqueue(
        session,
        "index",
        f"index:{question.external_id}:{question.revision}:{model_key}",
        {"question_id": question.external_id, "revision": question.revision, "model": model},
    )
    question.document.indexing_status = "queued"
    return task
