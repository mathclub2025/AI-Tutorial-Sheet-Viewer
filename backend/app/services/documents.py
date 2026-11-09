"""Stateless ingestion orchestration; job state belongs to AI, durability to Person 2."""

from app.core.errors import ServiceError, unavailable
from app.domain.models import (
    AgentDocumentJobRequest,
    DocumentDispatchResponse,
    DocumentJobStatusResponse,
    DocumentResultEvent,
    DocumentResultResponse,
)


class DocumentOrchestrator:
    def __init__(self, jobs, results):
        self.jobs, self.results = jobs, results

    async def dispatch(self, request, trace_id):
        if self.jobs is None:
            raise unavailable("Document-processing agent")
        ack = await self.jobs.submit(
            AgentDocumentJobRequest(**request.model_dump(), request_id=trace_id)
        )
        return DocumentDispatchResponse(
            **ack.model_dump(), document_id=request.document_id, request_id=trace_id
        )

    async def status(self, job_id, trace_id):
        if self.jobs is None:
            raise unavailable("Document-processing agent")
        job = await self.jobs.get(job_id, trace_id)
        if job is None:
            raise ServiceError("JOB_NOT_FOUND", "Document job was not found", 404)
        if job.job_id != job_id:
            raise ServiceError(
                "INVALID_UPSTREAM_RESPONSE", "Job identity does not match request", 502
            )
        return DocumentJobStatusResponse(**job.model_dump(), request_id=trace_id)

    async def result(self, job_id, payload, trace_id):
        if self.results is None:
            raise unavailable("Document result receiver")
        # Check against the authoritative AI job before touching the persistence service.
        job = await self.status(job_id, trace_id)
        for field in ("document_id", "document_version", "client_job_key", "source_type", "status"):
            if getattr(job, field) != getattr(payload, field):
                raise ServiceError(
                    "JOB_RESULT_CONFLICT", "Result does not match the authoritative job", 409
                )
        if payload.status == "completed" and job.extracted_count != len(payload.questions):
            raise ServiceError(
                "JOB_RESULT_CONFLICT", "Extracted question count does not match job", 409
            )
        event = DocumentResultEvent(**payload.model_dump(), job_id=job_id, request_id=trace_id)
        ack = await self.results.accept(event)
        for field in ("event_id", "job_id", "document_id", "document_version"):
            if getattr(ack, field) != getattr(event, field):
                raise ServiceError(
                    "INVALID_UPSTREAM_RESPONSE", "Result acknowledgement identity mismatch", 502
                )
        if (payload.status == "failed") != (ack.indexing_status == "not_applicable"):
            raise ServiceError("INVALID_UPSTREAM_RESPONSE", "Invalid indexing acknowledgement", 502)
        return DocumentResultResponse(**ack.model_dump(), request_id=trace_id)
