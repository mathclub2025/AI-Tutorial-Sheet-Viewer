"""Versioned administration API shared by direct data-service access and gateway routing."""

import time
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete, func, select

from app.core.errors import ServiceError
from app.data_service.auth import (
    DB,
    Administrator,
    Reviewer,
    SignedIn,
    Uploader,
    audit,
    bearer,
    hash_password,
    login,
    token_hash,
    user_view,
)
from app.data_service.review import (
    document_view,
    edit_question,
    get_question,
    review_question,
    review_view,
    task_view,
)
from app.data_service.service import _lock_idempotency_key
from app.data_service.tasks import invalidate_index, queue_dispatch, queue_index
from app.data_service.uploads import (
    check_document_access,
    confirm,
    get_document,
    initiate,
    storage_for,
)
from app.domain.management import (
    AssetUpload,
    DocumentClassification,
    DocumentPage,
    DocumentUpload,
    DocumentView,
    DownloadView,
    LoginRequest,
    PublicationRequest,
    QuestionEdit,
    QuestionPage,
    ReviewQuestion,
    ReviewRequest,
    ReviewStatus,
    SessionView,
    TaskPage,
    TaskView,
    UploadView,
    UserCreate,
    UserUpdate,
    UserView,
)
from app.domain.models import DocumentDispatchRequest, ErrorBody
from app.persistence.models import (
    AuditLog,
    AuthSession,
    Document,
    DocumentProcessingJob,
    IntegrationTask,
    QuestionRecord,
    User,
    utc_now,
)

ERRORS = {
    code: {"model": ErrorBody} for code in (401, 403, 404, 409, 410, 413, 422, 429, 502, 503, 504)
}
router = APIRouter(prefix="/api/v1", responses=ERRORS)
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


def login_limit(request: Request, payload: LoginRequest):
    allowed, _ = request.app.state.login_limiter.allow(
        "login:" + sha256(payload.email.strip().lower().encode()).hexdigest(),
        10,
        time.monotonic(),
    )
    if not allowed:
        raise ServiceError(
            "RATE_LIMITED", "Too many sign-in attempts; try again in one minute", 429
        )


@router.post(
    "/auth/login",
    response_model=SessionView,
    tags=["Authentication"],
    dependencies=[Depends(login_limit)],
)
def sign_in(payload: LoginRequest, session: DB, request: Request):
    return login(session, payload, request.app.state.settings.session_hours)


@router.get("/auth/me", response_model=UserView, tags=["Authentication"])
def me(user: SignedIn):
    return user_view(user)


@router.post("/auth/logout", tags=["Authentication"])
def logout(
    user: SignedIn,
    session: DB,
    credential: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
):
    session.execute(
        delete(AuthSession).where(AuthSession.token_hash == token_hash(credential.credentials))
    )
    return {"revoked": True}


@router.post("/admin/users", response_model=UserView, status_code=201, tags=["Admin users"])
def create_user(payload: UserCreate, session: DB, user: Administrator):
    email = payload.email.strip().lower()
    if "@" not in email or " " in email or not payload.name.strip():
        raise ServiceError("INVALID_USER", "Provide a name and email address", 422)
    _lock_idempotency_key(session, "user:" + email)
    if session.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise ServiceError("USER_EXISTS", "An account already exists for that email", 409)
    created = User(
        name=payload.name.strip(),
        email=email,
        role=payload.role,
        password_hash=hash_password(payload.password),
    )
    session.add(created)
    session.flush()
    audit(session, user, "user_created", "user", created.id, role=created.role)
    return user_view(created)


@router.get("/admin/users", response_model=list[UserView], tags=["Admin users"])
def list_users(session: DB, user: Administrator, offset: Offset = 0, limit: Limit = 50):
    return [
        user_view(item)
        for item in session.scalars(select(User).order_by(User.email).offset(offset).limit(limit))
    ]


@router.patch("/admin/users/{user_id}", response_model=UserView, tags=["Admin users"])
def update_user(user_id: UUID, payload: UserUpdate, session: DB, user: Administrator):
    if user_id == user.id:
        raise ServiceError(
            "SELF_CHANGE_FORBIDDEN", "Another administrator must change your own access", 409
        )
    target = session.get(User, user_id)
    if target is None:
        raise ServiceError("USER_NOT_FOUND", "User was not found", 404)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(target, key, value)
    session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    audit(
        session,
        user,
        "user_access_changed",
        "user",
        user_id,
        role=target.role,
        active=target.is_active,
    )
    return user_view(target)


@router.post("/admin/uploads", response_model=UploadView, status_code=201, tags=["Uploads"])
def create_upload(payload: DocumentUpload, session: DB, user: Uploader, request: Request):
    return initiate(session, payload, storage_for(request), user)


@router.post("/admin/assets/uploads", response_model=UploadView, status_code=201, tags=["Uploads"])
def create_asset_upload(payload: AssetUpload, session: DB, user: SignedIn, request: Request):
    return initiate(session, payload, storage_for(request), user)


@router.post("/admin/uploads/{upload_id}/confirm", response_model=UploadView, tags=["Uploads"])
def confirm_upload(upload_id: UUID, session: DB, user: SignedIn, request: Request):
    return confirm(session, upload_id, storage_for(request), user)


@router.get("/admin/documents", response_model=DocumentPage, tags=["Documents"])
def documents(session: DB, user: SignedIn, offset: Offset = 0, limit: Limit = 20):
    statement = select(Document)
    if user.role == "uploader":
        statement = statement.where(Document.uploaded_by == user.id)
    statement = statement.where(Document.document_type != "answer_sheet")
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    items = session.scalars(
        statement.order_by(Document.created_at.desc(), Document.id).offset(offset).limit(limit)
    )
    return {
        "items": [document_view(d, session) for d in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/admin/documents/{document_id}", response_model=DocumentView, tags=["Documents"])
def document_detail(document_id: str, session: DB, user: SignedIn):
    document = get_document(session, document_id)
    check_document_access(document, user)
    return document_view(document, session)


@router.get(
    "/admin/documents/{document_id}/download", response_model=DownloadView, tags=["Documents"]
)
def document_download(document_id: str, session: DB, user: SignedIn, request: Request):
    document = get_document(session, document_id)
    check_document_access(document, user)
    storage = storage_for(request)
    return {
        "document": document_view(document),
        "download_url": storage.download_url(document.object_key),
        "expires_in_seconds": storage.settings.signed_url_expiry_seconds,
    }


@router.post(
    "/admin/documents/{document_id}/process",
    response_model=TaskView,
    status_code=202,
    tags=["Documents"],
)
def process_document(
    document_id: str, payload: DocumentDispatchRequest, session: DB, user: Uploader
):
    document = get_document(session, document_id, lock=True)
    check_document_access(document, user)
    if (
        payload.document_id != document_id
        or payload.document_version != document.current_version
        or payload.source_type != document.source_type
    ):
        raise ServiceError(
            "DOCUMENT_VERSION_CONFLICT", "Processing request does not match the document", 409
        )
    task = queue_dispatch(session, document, payload.client_job_key)
    audit(session, user, "processing_queued", "document", document_id, task_id=str(task.id))
    return task_view(task)


@router.get("/admin/documents/{document_id}/processing-jobs", tags=["Documents"])
def processing_jobs(
    document_id: str, session: DB, user: SignedIn, offset: Offset = 0, limit: Limit = 20
):
    document = get_document(session, document_id)
    check_document_access(document, user)
    rows = session.scalars(
        select(DocumentProcessingJob)
        .where(DocumentProcessingJob.document_id == document.id)
        .order_by(DocumentProcessingJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return {
        "items": [
            {
                "client_job_key": r.client_job_key,
                "ai_job_id": r.ai_job_id,
                "status": r.status,
                "attempts": r.attempts,
                "error": r.error_message,
            }
            for r in rows
        ]
    }


@router.post(
    "/admin/documents/{document_id}/publication", response_model=DocumentView, tags=["Publication"]
)
def publication(document_id: str, payload: PublicationRequest, session: DB, user: Reviewer):
    document = get_document(session, document_id, lock=True)
    if payload.visibility == "public" and document.document_type != "answer_sheet":
        approved = session.scalar(
            select(QuestionRecord.id)
            .where(
                QuestionRecord.document_id == document.id,
                QuestionRecord.status == "approved",
            )
            .limit(1)
        )
        if approved is None:
            raise ServiceError(
                "NOT_REVIEWED", "Approve at least one question before publication", 409
            )
    document.visibility = payload.visibility
    audit(
        session, user, "publication_changed", "document", document_id, visibility=payload.visibility
    )
    return document_view(document, session)


@router.get("/admin/questions", response_model=QuestionPage, tags=["Review"])
def review_queue(
    session: DB,
    user: SignedIn,
    document_id: str | None = None,
    status: ReviewStatus | None = None,
    offset: Offset = 0,
    limit: Limit = 20,
):
    statement = select(QuestionRecord).join(QuestionRecord.document)
    if user.role == "uploader":
        statement = statement.where(Document.uploaded_by == user.id)
    if document_id:
        statement = statement.where(Document.external_id == document_id)
    if status:
        statement = statement.where(QuestionRecord.status == status)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    items = session.scalars(
        statement.order_by(QuestionRecord.created_at, QuestionRecord.id).offset(offset).limit(limit)
    )
    return {
        "items": [review_view(session, q) for q in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/admin/questions/{question_id}", response_model=ReviewQuestion, tags=["Review"])
def question_detail(question_id: str, session: DB, user: SignedIn):
    return review_view(session, get_question(session, question_id, user))


@router.patch("/admin/questions/{question_id}", response_model=ReviewQuestion, tags=["Review"])
def edit(question_id: str, payload: QuestionEdit, session: DB, user: Reviewer):
    return edit_question(
        session, get_question(session, question_id, user, lock=True), payload, user
    )


@router.post(
    "/admin/questions/{question_id}/review", response_model=ReviewQuestion, tags=["Review"]
)
def review(question_id: str, payload: ReviewRequest, session: DB, user: Reviewer, request: Request):
    return review_question(
        session,
        get_question(session, question_id, user, lock=True),
        payload,
        user,
        request.app.state.settings.embedding_model,
    )


@router.get("/admin/assets/{asset_id}/download", tags=["Review"])
def asset_download(asset_id: UUID, session: DB, user: SignedIn, request: Request):
    from app.persistence.models import ContentAsset

    asset = session.get(ContentAsset, asset_id)
    if asset is None:
        raise ServiceError("ASSET_NOT_FOUND", "Asset was not found", 404)
    check_document_access(session.get(Document, asset.document_id), user)
    storage = storage_for(request)
    return {
        "url": storage.download_url(asset.object_key),
        "expires_in_seconds": storage.settings.signed_url_expiry_seconds,
    }


@router.post(
    "/admin/questions/{question_id}/reindex",
    response_model=TaskView,
    status_code=202,
    tags=["Operations"],
)
def reindex(question_id: str, session: DB, user: Reviewer, request: Request):
    question = get_question(session, question_id, user, lock=True)
    if question.status != "approved":
        raise ServiceError("NOT_APPROVED", "Only approved questions can be indexed", 409)
    task = queue_index(session, question, request.app.state.settings.embedding_model)
    if task.status in {"succeeded", "failed"}:
        task.status, task.attempts, task.last_error = "queued", 0, None
        task.next_attempt_at = utc_now()
    audit(session, user, "reindex_requested", "question", question_id)
    return task_view(task)


@router.get("/admin/tasks", response_model=TaskPage, tags=["Operations"])
def tasks(session: DB, user: Administrator, offset: Offset = 0, limit: Limit = 20):
    total = session.scalar(select(func.count()).select_from(IntegrationTask))
    rows = session.scalars(
        select(IntegrationTask)
        .order_by(IntegrationTask.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return {"items": [task_view(t) for t in rows], "total": total, "offset": offset, "limit": limit}


@router.post("/admin/tasks/{task_id}/retry", response_model=TaskView, tags=["Operations"])
def retry_task(task_id: UUID, session: DB, user: Administrator):
    task = session.scalar(
        select(IntegrationTask).where(IntegrationTask.id == task_id).with_for_update()
    )
    if task is None:
        raise ServiceError("TASK_NOT_FOUND", "Task was not found", 404)
    if task.status != "failed":
        raise ServiceError("TASK_NOT_FAILED", "Only failed tasks can be retried", 409)
    task.status, task.attempts, task.last_error = "queued", 0, None
    task.next_attempt_at = utc_now()
    audit(session, user, "task_retried", "task", task.id)
    return task_view(task)


@router.get("/admin/audit-events", tags=["Operations"])
def audit_events(session: DB, user: Administrator, offset: Offset = 0, limit: Limit = 20):
    rows = session.scalars(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
        .offset(offset)
        .limit(limit)
    )
    return {
        "items": [
            {
                "id": str(r.id),
                "actor_id": str(r.actor_id) if r.actor_id else None,
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "details": r.details,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


@router.patch("/admin/documents/{document_id}/classification", response_model=DocumentView, tags=["Documents"])
def classify_document(document_id: str, payload: DocumentClassification, session: DB, user: Reviewer):
    document = get_document(session, document_id, lock=True)
    if document.source_type != payload.expected_source_type:
        raise ServiceError("REVISION_CONFLICT", "Reload the batch before changing its classification", 409)
    if document.processing_status != "succeeded":
        raise ServiceError("NOT_PROCESSED", "Wait for extraction before changing classification", 409)
    if document.source_type == payload.source_type:
        return document_view(document, session)
    document.source_type = payload.source_type
    document.document_type = "tutorial_sheet" if payload.source_type == "tutorial" else "question_paper"
    document.visibility = "private"
    for question in session.scalars(select(QuestionRecord).where(QuestionRecord.document_id == document.id).with_for_update()):
        question.status = "pending_review"
        question.revision += 1
        for answer in question.answers:
            answer.review_status = "pending_review"
        invalidate_index(session, question)
    audit(session, user, "document_classified", "document", document_id, source_type=payload.source_type)
    session.flush()
    return document_view(document, session)
