import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ServiceError
from app.domain.models import (
    DocumentResultAck,
    DocumentResultEvent,
    FilterCatalog,
    QueryEvent,
    Question,
    SearchEnvelope,
    SearchRequest,
)
from app.persistence.database import session_scope

IdentifierPath = Annotated[
    str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
]


def require_person1_token(
    request: Request, token: str | None = Header(None, alias="X-Internal-Token")
):
    configured = request.app.state.settings.person2_inbound_token
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Person 2 internal token is not configured",
        )
    expected = configured.get_secret_value()
    if not token or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token"
        )


router = APIRouter(
    prefix="/internal/v1",
    tags=["Person 2 data service"],
    dependencies=[Depends(require_person1_token)],
)


def readiness(request: Request):
    try:
        with request.app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
            session.execute(text("SELECT 1 FROM documents LIMIT 0"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Data service database is unavailable",
        ) from exc
    return {"status": "ready"}


@router.post("/search", response_model=SearchEnvelope)
def search(payload: SearchRequest, request: Request):
    with session_scope(request.app.state.session_factory) as session:
        return request.app.state.data_service.search(session, payload)


@router.get("/questions/{question_id}", response_model=Question)
def get_question(question_id: IdentifierPath, request: Request):
    with session_scope(request.app.state.session_factory) as session:
        return request.app.state.data_service.get_question(session, question_id)


@router.get("/questions/{question_id}/similar", response_model=SearchEnvelope)
def similar_questions(
    question_id: IdentifierPath,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
):
    with session_scope(request.app.state.session_factory) as session:
        return request.app.state.data_service.similar(session, question_id, limit)


@router.get("/catalog", response_model=FilterCatalog)
def catalog(request: Request):
    with session_scope(request.app.state.session_factory) as session:
        return request.app.state.data_service.catalog(session)


@router.post("/query-events", status_code=status.HTTP_200_OK)
def record_query_event(event: QueryEvent, request: Request):
    with session_scope(request.app.state.session_factory) as session:
        request.app.state.data_service.record_query_event(session, event)
    return {"accepted": True}


@router.post("/document-results", response_model=DocumentResultAck)
def accept_document_result(event: DocumentResultEvent, request: Request):
    with session_scope(request.app.state.session_factory) as session:
        return request.app.state.data_service.accept_document_result(session, event)


def install_data_service_error_handler(app):
    @app.exception_handler(ServiceError)
    async def handle_service_error(request: Request, exc: ServiceError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.code,
                "message": exc.message,
                "request_id": request.headers.get("X-Request-ID", ""),
                "details": [],
            },
        )
