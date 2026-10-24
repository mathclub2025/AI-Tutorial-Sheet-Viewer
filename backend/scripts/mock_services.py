"""LOCAL TEST DOUBLES ONLY. Volatile memory, canned AI; never deploy these services."""

import os

from fastapi import Depends, FastAPI, Header, HTTPException

from app.adapters.demo import DemoAI, DemoQuestions
from app.domain.models import (
    AgentAnswerRequest,
    AgentDocumentJobRequest,
    AgentExplainRequest,
    DocumentJobStatus,
    DocumentResultEvent,
    QueryEvent,
    SearchRequest,
)

TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "integration-demo-token")


def auth(x_internal_token: str | None = Header(default=None)):
    if x_internal_token != TOKEN:
        raise HTTPException(401, "Invalid mock service credential")


p2 = FastAPI(title="MOCK Person 2 service", dependencies=[Depends(auth)])
ai = FastAPI(title="MOCK AI gateway", dependencies=[Depends(auth)])
questions, answers = DemoQuestions(), DemoAI()
events, jobs, job_keys, results = {}, {}, {}, {}


@p2.get("/health/ready")
@ai.get("/health/ready")
async def ready():
    return {"status": "ready"}


@p2.post("/internal/v1/search")
async def search(payload: SearchRequest):
    return {"items": await questions.search(payload, "mock")}


@p2.get("/internal/v1/catalog")
async def catalog():
    return await questions.catalog("mock")


@p2.get("/internal/v1/questions/{question_id}")
async def get(question_id: str):
    q = await questions.get(question_id, "mock")
    if q is None:
        raise HTTPException(404)
    return q


@p2.get("/internal/v1/questions/{question_id}/similar")
async def similar(question_id: str, limit: int = 5):
    return {"items": await questions.similar(question_id, limit, "mock")}


@p2.post("/internal/v1/query-events")
async def capture(event: QueryEvent):
    events.setdefault(event.event_id, event)
    return {"accepted": True}  # MOCK ONLY: not a durable acknowledgement.


@ai.post("/internal/v1/answer")
async def answer(payload: AgentAnswerRequest):
    return await answers.answer(payload)


@ai.post("/internal/v1/explain")
async def explain(payload: AgentExplainRequest):
    return await answers.explain(payload)


@ai.post("/internal/v1/document-jobs", status_code=202)
async def submit(payload: AgentDocumentJobRequest):
    key = payload.client_job_key
    identity = (payload.document_id, payload.document_version, payload.source_type)
    if key in job_keys and job_keys[key][0] != identity:
        raise HTTPException(409, "Job key reused for another document")
    if key not in job_keys:
        job_id = f"mock-job-{len(jobs) + 1}"
        jobs[job_id] = DocumentJobStatus(
            **payload.model_dump(exclude={"request_id"}),
            job_id=job_id,
            status="completed",
            progress=100,
            extracted_count=1,
        )
        job_keys[key] = (identity, job_id)
    return {"status": "queued", "job_id": job_keys[key][1]}


@ai.get("/internal/v1/document-jobs/{job_id}")
async def job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404)
    return jobs[job_id]


@p2.post("/internal/v1/document-results")
async def accept(event: DocumentResultEvent):
    # Ignore transport trace on replay; reject changed business content under the same event ID.
    data = event.model_dump(mode="json", exclude={"request_id"})
    if event.event_id in results and results[event.event_id] != data:
        raise HTTPException(409, "Changed event body")
    results[event.event_id] = data
    return {
        "accepted": True,
        "event_id": event.event_id,
        "job_id": event.job_id,
        "document_id": event.document_id,
        "document_version": event.document_version,
        "indexing_status": "not_applicable" if event.status == "failed" else "pending",
    }
