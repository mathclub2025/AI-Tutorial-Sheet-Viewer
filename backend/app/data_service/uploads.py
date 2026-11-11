"""Durable, owner-scoped upload authorizations and verified document registration."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.errors import ServiceError
from app.data_service.auth import audit
from app.data_service.service import DataService, _lock_idempotency_key, _normalized_datetime
from app.data_service.tasks import queue_dispatch
from app.domain.management import AssetUpload, DocumentUpload, UploadView
from app.persistence.models import ContentAsset, Document, UploadIntent, utc_now


def storage_for(request):
    storage = request.app.state.storage
    if storage is None:
        raise ServiceError("STORAGE_NOT_CONFIGURED", "Configure object storage for uploads", 503)
    return storage


def get_document(session, document_id, *, lock=False):
    statement = select(Document).where(Document.external_id == document_id)
    if lock:
        statement = statement.with_for_update()
    document = session.scalar(statement)
    if document is None:
        raise ServiceError("DOCUMENT_NOT_FOUND", "Document was not found", 404)
    return document


def check_document_access(document, user):
    if user.role == "uploader" and document.uploaded_by != user.id:
        raise ServiceError("FORBIDDEN", "This document belongs to another uploader", 403)


def upload_view(session, intent, storage):
    data = intent.request_data
    confirmed = intent.confirmed_at is not None
    remaining = int((_normalized_datetime(intent.expires_at) - utc_now()).total_seconds())
    if not confirmed and remaining <= 0:
        raise ServiceError("UPLOAD_EXPIRED", "Create a new upload with a new client key", 410)
    document = session.get(Document, intent.document_id) if intent.document_id else None
    return UploadView(
        id=intent.id,
        upload_url=None
        if confirmed
        else storage.upload_url(
            intent.object_key,
            data["content_type"],
            data["size_bytes"],
            remaining,
        ),
        required_headers={}
        if confirmed
        else {
            "Content-Type": data["content_type"],
            "Content-Length": str(data["size_bytes"]),
        },
        expires_at=intent.expires_at,
        confirmed=confirmed,
        document_id=document.external_id if document else None,
        asset_id=intent.asset_id,
    )


def initiate(session, payload, storage, user=None):
    purpose = "document" if isinstance(payload, DocumentUpload) else payload.kind
    identity = str(user.id) if user else "ai"
    key = identity + ":" + payload.client_upload_key
    _lock_idempotency_key(session, "upload:" + key)
    data = payload.model_dump(mode="json")
    existing = session.scalar(select(UploadIntent).where(UploadIntent.client_key == key))
    if existing is not None:
        if existing.request_data != data or existing.purpose != purpose:
            raise ServiceError("UPLOAD_KEY_CONFLICT", "Upload key has different metadata", 409)
        return upload_view(session, existing, storage)
    parent = None
    if isinstance(payload, AssetUpload):
        if payload.content_type not in {"image/png", "image/jpeg"}:
            raise ServiceError(
                "INVALID_ASSET_TYPE", "Question and solution crops must be images", 422
            )
        parent = get_document(session, payload.document_id)
        if parent.current_version != payload.document_version:
            raise ServiceError(
                "DOCUMENT_VERSION_CONFLICT", "Asset has a stale document version", 409
            )
        if user:
            check_document_access(parent, user)
    # Answer sheets are stored for explicit solution mapping; never extract them as questions.
    if (
        isinstance(payload, DocumentUpload)
        and payload.document_type == "answer_sheet"
        and payload.process
    ):
        raise ServiceError("SOLUTION_MAPPING_REQUIRED", "Set process=false for answer sheets", 422)
    try:
        key = storage.new_object_key(
            payload.filename,
            payload.content_type,
            payload.size_bytes,
            storage.settings.max_upload_bytes,
        )
        sealed_key = storage.new_object_key(
            payload.filename,
            payload.content_type,
            payload.size_bytes,
            storage.settings.max_upload_bytes,
        )
    except ValueError as exc:
        raise ServiceError("INVALID_UPLOAD", str(exc), 422) from exc
    intent = UploadIntent(
        owner_id=user.id if user else None,
        client_key=identity + ":" + payload.client_upload_key,
        purpose=purpose,
        request_data=data,
        object_key=key,
        sealed_key=sealed_key,
        expires_at=utc_now() + timedelta(seconds=storage.settings.signed_url_expiry_seconds),
        document_id=parent.id if parent else None,
    )
    session.add(intent)
    session.flush()
    audit(session, user, "upload_authorized", "upload", intent.id, purpose=purpose)
    return upload_view(session, intent, storage)


def confirm(session, upload_id, storage, user=None):
    intent = session.scalar(
        select(UploadIntent).where(UploadIntent.id == upload_id).with_for_update()
    )
    if intent is None:
        raise ServiceError("UPLOAD_NOT_FOUND", "Upload authorization was not found", 404)
    # A service credential cannot redeem a human upload, and vice versa.
    if intent.owner_id != (user.id if user else None):
        raise ServiceError("FORBIDDEN", "Upload authorization belongs to another caller", 403)
    if intent.confirmed_at:
        return upload_view(session, intent, storage)
    if _normalized_datetime(intent.expires_at) <= utc_now():
        raise ServiceError("UPLOAD_EXPIRED", "Create a new upload authorization", 410)
    data = intent.request_data
    verified = storage.seal_upload(
        intent.object_key,
        intent.sealed_key,
        expected_size_bytes=data["size_bytes"],
        expected_content_type=data["content_type"],
        expected_sha256=data["sha256"],
    )
    if intent.purpose == "document":
        subject = DataService._get_or_create_subject(session, data["subject"])
        module = (
            DataService._get_or_create_module(session, subject, data["module"])
            if data["module"]
            else None
        )
        document = Document(
            external_id=str(uuid4()),
            title=data["title"],
            document_type=data["document_type"],
            source_type=data["source_type"],
            original_filename=data["filename"],
            object_key=intent.sealed_key,
            bucket_name=verified["bucket_name"],
            mime_type=verified["mime_type"],
            file_size_bytes=verified["file_size_bytes"],
            sha256=verified["sha256"],
            uploaded_by=intent.owner_id,
            subject=subject,
            module=module,
            publication_year=data["year"],
            visibility="private",
            current_version="v1",
        )
        session.add(document)
        session.flush()
        intent.document_id = document.id
        if data["process"]:
            queue_dispatch(session, document, f"{document.external_id}:v1:extract")
    else:
        document = get_document(session, data["document_id"], lock=True)
        if document.current_version != data["document_version"]:
            raise ServiceError(
                "DOCUMENT_VERSION_CONFLICT", "Asset has a stale document version", 409
            )
        asset = ContentAsset(
            document_id=document.id,
            document_version=document.current_version,
            kind=intent.purpose,
            object_key=intent.sealed_key,
            mime_type=verified["mime_type"],
            size_bytes=verified["file_size_bytes"],
            sha256=verified["sha256"],
        )
        session.add(asset)
        session.flush()
        intent.asset_id = asset.id
    intent.confirmed_at = utc_now()
    audit(session, user, "upload_confirmed", "upload", intent.id, document_id=document.external_id)
    return upload_view(session, intent, storage)
