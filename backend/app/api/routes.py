from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, Request

from app.adapters.http_clients import BaseHTTPAdapter, parse
from app.api.deps import get_orchestrator, get_trace_id
from app.core.errors import ServiceError
from app.core.security import (
    require_api_key,
    require_callback_token,
    require_dispatch_token,
    require_operations_token,
)
from app.domain.management import AssetLinks, SemanticSearchRequest
from app.domain.models import (
    AskRequest,
    AskResponse,
    CatalogResponse,
    DocumentDispatchRequest,
    DocumentDispatchResponse,
    DocumentJobStatusResponse,
    DocumentResult,
    DocumentResultResponse,
    ErrorBody,
    ExplainRequest,
    ExplainResponse,
    QueryEvent,
    Question,
    SearchEnvelope,
    SearchRequest,
    SearchResponse,
    SimilarResponse,
)
from app.services.orchestrator import Orchestrator

ERRORS = {
    code: {"model": ErrorBody} for code in (400, 401, 404, 409, 413, 422, 429, 500, 502, 503, 504)
}
router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)], responses=ERRORS)
Engine = Annotated[Orchestrator, Depends(get_orchestrator)]
Trace = Annotated[str, Depends(get_trace_id)]
QuestionID = Annotated[
    str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
]
JobID = QuestionID


@router.get("/catalog", response_model=CatalogResponse, tags=["Search"])
async def catalog(engine: Engine, trace_id: Trace):
    """Return valid filter combinations for dependent frontend dropdowns."""
    return await engine.catalog(trace_id)


@router.post("/search", response_model=SearchResponse, tags=["Search"])
async def search(payload: SearchRequest, engine: Engine, trace_id: Trace):
    return await engine.search(payload, trace_id)


def extended_data_adapter(request):
    cfg = request.app.state.settings
    client = request.app.state.integration_client
    if client is None or not cfg.person2_base_url:
        raise ServiceError("NOT_CONFIGURED", "This operation requires the data service", 503)
    return BaseHTTPAdapter(cfg.person2_base_url, client, cfg.token_for("person2_service_token"), settings=cfg)


@router.post("/search/semantic", response_model=SearchResponse, tags=["Search"])
async def semantic_search(payload: SemanticSearchRequest, request: Request, engine: Engine, trace_id: Trace):
    adapter = extended_data_adapter(request)
    captured = await engine._capture(QueryEvent(event_type="search", request_id=trace_id, query=payload.query, filters=payload.filters))
    result = parse(SearchEnvelope, await adapter.request(
        "POST", "/internal/v1/search/semantic", trace_id, json=payload.model_dump(mode="json"),
    ))
    hits = engine._hits(result.items, payload.filters)[:payload.limit]
    return SearchResponse(items=hits, total=len(hits), captured=captured, request_id=trace_id)


@router.get("/questions/{question_id}/assets", response_model=AssetLinks, tags=["Questions"])
async def question_assets(question_id: QuestionID, request: Request, trace_id: Trace):
    adapter = extended_data_adapter(request)
    result = await adapter.request("GET", f"/internal/v1/questions/{quote(question_id, safe='')}/assets", trace_id,
                                   retry_safe=True, allow_not_found=True)
    if result is None:
        raise ServiceError("QUESTION_NOT_FOUND", "Question was not found", 404)
    links = parse(AssetLinks, result)
    if links.question_id != question_id:
        raise ServiceError("INVALID_UPSTREAM_RESPONSE", "Asset response has the wrong question", 502)
    return links


@router.post("/ask", response_model=AskResponse, tags=["AI Orchestration"])
async def ask(payload: AskRequest, engine: Engine, trace_id: Trace):
    return await engine.ask(payload, trace_id)


@router.get("/questions/{question_id}", response_model=Question, tags=["Questions"])
async def get_question(question_id: QuestionID, engine: Engine, trace_id: Trace):
    return await engine.get_question(question_id, trace_id)


@router.get("/questions/{question_id}/similar", response_model=SimilarResponse, tags=["Questions"])
async def similar(
    question_id: QuestionID,
    engine: Engine,
    trace_id: Trace,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
):
    return await engine.similar(question_id, limit, trace_id)


@router.post(
    "/questions/{question_id}/explain", response_model=ExplainResponse, tags=["AI Orchestration"]
)
async def explain(
    question_id: QuestionID, payload: ExplainRequest, engine: Engine, trace_id: Trace
):
    return await engine.explain(question_id, payload, trace_id)


internal_router = APIRouter(
    prefix="/internal/v1", tags=["Document orchestration"], responses=ERRORS
)


@internal_router.post(
    "/documents/dispatch",
    response_model=DocumentDispatchResponse,
    dependencies=[Depends(require_dispatch_token)],
)
async def dispatch_document(payload: DocumentDispatchRequest, request: Request, trace_id: Trace):
    """Keep v0.1 HTTP 200 acknowledgement. Processing continues at the AI service."""
    return await request.app.state.documents.dispatch(payload, trace_id)


@internal_router.get(
    "/document-jobs/{job_id}",
    response_model=DocumentJobStatusResponse,
    dependencies=[Depends(require_dispatch_token)],
)
async def document_status(job_id: JobID, request: Request, trace_id: Trace):
    """Private extraction status. Completed does not imply indexed/searchable."""
    return await request.app.state.documents.status(job_id, trace_id)


@internal_router.post(
    "/document-jobs/{job_id}/result",
    response_model=DocumentResultResponse,
    dependencies=[Depends(require_callback_token)],
)
async def document_result(
    job_id: JobID, payload: DocumentResult, request: Request, trace_id: Trace
):
    """Validate AI terminal callback and await Person 2's durability acknowledgement."""
    return await request.app.state.documents.result(job_id, payload, trace_id)


@internal_router.get(
    "/metrics", dependencies=[Depends(require_operations_token)], tags=["Operations"]
)
async def metrics(request: Request):
    return request.app.state.stats.snapshot()
