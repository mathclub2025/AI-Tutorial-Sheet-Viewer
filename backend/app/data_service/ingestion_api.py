"""Narrow AI credential for document downloads and crop uploads."""

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from app.core.errors import ServiceError
from app.data_service.auth import DB
from app.data_service.review import asset_links, document_view
from app.data_service.semantic import semantic_search
from app.data_service.service import DataService
from app.data_service.uploads import confirm, get_document, initiate, storage_for
from app.domain.management import AssetUpload, DownloadView, SemanticSearchRequest, UploadView
from app.domain.models import SearchEnvelope
from app.persistence.models import QuestionRecord


def require_ai_data(request: Request, token: str | None = Header(None, alias="X-Internal-Token")):
    secret = request.app.state.settings.ai_data_token
    if not secret:
        raise ServiceError("AUTH_NOT_CONFIGURED", "Configure the AI data access credential", 503)
    if not token or not secrets.compare_digest(token.encode(), secret.get_secret_value().encode()):
        raise ServiceError("UNAUTHORIZED", "Invalid AI data credential", 401)


router = APIRouter(
    prefix="/internal/v1/ingestion", dependencies=[Depends(require_ai_data)], tags=["AI ingestion"]
)


@router.get("/documents/{document_id}", response_model=DownloadView)
def download(document_id: str, document_version: str, session: DB, request: Request):
    document = get_document(session, document_id)
    if document.current_version != document_version:
        raise ServiceError(
            "DOCUMENT_VERSION_CONFLICT", "Document version is no longer current", 409
        )
    storage = storage_for(request)
    return {
        "document": document_view(document),
        "download_url": storage.download_url(document.object_key),
        "expires_in_seconds": storage.settings.signed_url_expiry_seconds,
    }


@router.post("/assets/uploads", response_model=UploadView, status_code=201)
def asset_upload(payload: AssetUpload, session: DB, request: Request):
    return initiate(session, payload, storage_for(request))


@router.post("/assets/uploads/{upload_id}/confirm", response_model=UploadView)
def asset_confirm(upload_id: UUID, session: DB, request: Request):
    return confirm(session, upload_id, storage_for(request))


def add_student_extensions(router):
    # This router already requires the gateway-to-data service credential.
    @router.post("/search/semantic", response_model=SearchEnvelope, tags=["Semantic search"])
    def semantic(payload: SemanticSearchRequest, session: DB, request: Request):
        return semantic_search(
            session, payload, request.app.state.embeddings, request.app.state.settings
        )

    @router.get("/questions/{question_id}/assets", tags=["Question assets"])
    def assets(question_id: str, session: DB, request: Request):
        question = session.scalar(
            DataService()._question_query().where(QuestionRecord.external_id == question_id)
        )
        if question is None:
            raise ServiceError("QUESTION_NOT_FOUND", "Question was not found", 404)
        return asset_links(session, question, storage_for(request))
