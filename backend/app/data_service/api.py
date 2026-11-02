import hmac
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from app.core.errors import ServiceError
from app.domain.models import (
    DocumentDeletionResponse,
    DocumentDownloadResponse,
    DocumentResultAck,
    DocumentResultEvent,
    DocumentUploadAuthorization,
    DocumentUploadConfirmation,
    DocumentUploadRequest,
    DocumentUploadResponse,
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


@router.post("/documents/uploads", response_model=DocumentUploadAuthorization)
def authorize_upload(payload: DocumentUploadRequest, request: Request):
    with session_scope(request.app.state.session_factory) as session:
        authorization, document = request.app.state.data_service.authorize_upload(session, payload)
        return DocumentUploadAuthorization(
            document_id=document.external_id,
            document_version=document.current_version,
            object_key=authorization.object_key,
            upload_url=authorization.url,
            required_headers=authorization.required_headers,
            expires_in_seconds=authorization.expires_in_seconds,
            max_size_bytes=authorization.max_size_bytes,
        )


@router.post("/documents/{document_id}/uploads/confirm", response_model=DocumentUploadResponse)
def confirm_upload(
    document_id: IdentifierPath,
    payload: DocumentUploadConfirmation,
    request: Request,
):
    if payload.document_id != document_id:
        raise HTTPException(status_code=409, detail="Document identity does not match path")
    with session_scope(request.app.state.session_factory) as session:
        document = request.app.state.data_service.confirm_upload(session, payload)
        return DocumentUploadResponse(
            document_id=document.external_id,
            document_version=document.current_version,
            status="succeeded",
            processing_status=document.processing_status,
            indexing_status=document.indexing_status,
            sha256=document.sha256,
        )


@router.get("/documents/{document_id}/download", response_model=DocumentDownloadResponse)
def download_document(document_id: IdentifierPath, request: Request):
    with session_scope(request.app.state.session_factory) as session:
        document, url, expires = request.app.state.data_service.get_download_url(
            session, document_id
        )
        return DocumentDownloadResponse(
            document_id=document.external_id,
            document_version=document.current_version,
            url=url,
            expires_in_seconds=expires,
        )


@router.get("/documents/{document_id}/content")
def retrieve_document_content(document_id: IdentifierPath, request: Request):
    with session_scope(request.app.state.session_factory) as session:
        document, url, expires = request.app.state.data_service.get_download_url(
            session, document_id
        )
    if expires is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Backend Worker retrieval is available only for public delivery",
        )

    client = httpx.Client(follow_redirects=False, timeout=30.0)
    try:
        upstream = client.send(client.build_request("GET", url), stream=True)
    except httpx.HTTPError as exc:
        client.close()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve the document from the delivery Worker",
        ) from exc

    if upstream.status_code < 200 or upstream.status_code >= 300:
        upstream.close()
        client.close()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The delivery Worker could not retrieve the document",
        )

    headers = {}
    for header in ("content-type", "content-length", "content-disposition", "etag"):
        value = upstream.headers.get(header)
        if value is not None:
            headers[header] = value
    return StreamingResponse(
        upstream.iter_bytes(),
        status_code=upstream.status_code,
        headers=headers,
        background=BackgroundTask(_close_upstream, upstream, client),
    )


def _close_upstream(upstream: httpx.Response, client: httpx.Client):
    upstream.close()
    client.close()


@router.delete("/documents/{document_id}", response_model=DocumentDeletionResponse)
def delete_document(document_id: IdentifierPath, request: Request):
    with session_scope(request.app.state.session_factory) as session:
        deleted_id = request.app.state.data_service.delete_document(session, document_id)
    return DocumentDeletionResponse(document_id=deleted_id, deleted=True)


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
