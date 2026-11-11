"""Review and publication stay separate; every content mutation invalidates its index."""

from uuid import UUID

from sqlalchemy import or_, select

from app.core.errors import ServiceError
from app.data_service.auth import audit
from app.data_service.service import DataService
from app.data_service.tasks import invalidate_index, queue_index
from app.data_service.uploads import check_document_access
from app.domain.management import DocumentView, ReviewQuestion, TaskView
from app.persistence.models import Answer, ContentAsset, Document, QuestionRecord, QuestionTopic


def document_view(document, session=None):
    counts = {"question_count": 0, "approved_count": 0, "flagged_count": 0, "pending_count": 0}
    if session is not None:
        from sqlalchemy import func
        rows = session.execute(select(
            QuestionRecord.status, QuestionRecord.flag_note.is_not(None), func.count()
        ).where(
            QuestionRecord.document_id == document.id,
            or_(QuestionRecord.document_version == document.current_version, QuestionRecord.document_version.is_(None)),
            QuestionRecord.status.not_in(["archived", "rejected"]),
        ).group_by(QuestionRecord.status, QuestionRecord.flag_note.is_not(None)))
        for status, flagged, count in rows:
            counts["question_count"] += count
            key = "flagged_count" if flagged else "approved_count" if status == "approved" else "pending_count"
            counts[key] += count
    return DocumentView(
        id=document.external_id,
        title=document.title,
        document_type=document.document_type,
        source_type=document.source_type,
        document_version=document.current_version,
        filename=document.original_filename,
        size_bytes=document.file_size_bytes,
        subject=document.subject.name if document.subject else None,
        module=document.module.name if document.module else None,
        year=document.publication_year,
        visibility=document.visibility,
        processing_status=document.processing_status,
        indexing_status=document.indexing_status,
        created_at=document.created_at,
        **counts,
    )


def task_view(task):
    return TaskView.model_validate(task, from_attributes=True)


def first_answer(session, question):
    return session.scalar(
        select(Answer)
        .where(Answer.question_id == question.id)
        .order_by(
            Answer.created_at,
            Answer.id,
        )
        .limit(1)
    )


def review_view(session, question):
    answer = first_answer(session, question)
    source = (
        session.get(Document, answer.source_document_id)
        if answer and answer.source_document_id
        else None
    )
    topics = sorted(
        question.topics, key=lambda a: (a.assigned_by != "manual", a.topic.name.casefold())
    )
    return ReviewQuestion(
        id=question.external_id,
        document_id=question.document.external_id,
        revision=question.revision,
        status=question.status,
        text=question.question_text,
        subject=question.subject.name if question.subject else None,
        module=question.module.name if question.module else None,
        topic=topics[0].topic.name if topics else None,
        page_number=question.page_start,
        question_number=question.question_number,
        official_solution=answer.answer_text if answer else None,
        solution_status=answer.review_status if answer else None,
        solution_document_id=source.external_id if source else None,
        question_asset_id=question.question_asset_id,
        solution_asset_id=answer.solution_asset_id if answer else None,
        topics=[assignment.topic.name for assignment in topics],
        difficulty=question.difficulty,
        flag_note=question.flag_note,
        source_type=question.document.source_type,
        year=question.document.publication_year,
        document_version=question.document.current_version,
    )


def get_question(session, question_id, user, *, lock=False):
    statement = select(QuestionRecord).where(QuestionRecord.external_id == question_id)
    if lock:
        statement = statement.with_for_update()
    question = session.scalar(statement)
    if question is None:
        raise ServiceError("QUESTION_NOT_FOUND", "Question was not found", 404)
    check_document_access(question.document, user)
    return question


def check_revision(question, revision):
    if question.revision != revision:
        raise ServiceError("REVISION_CONFLICT", "Reload the question before saving changes", 409)
    if question.document_version not in {None, question.document.current_version}:
        raise ServiceError(
            "DOCUMENT_VERSION_CONFLICT", "Question belongs to an old document version", 409
        )


def validated_asset(session, asset_id, kind, document):
    if asset_id is None:
        return None
    try:
        asset = session.get(ContentAsset, UUID(str(asset_id)))
    except ValueError as exc:
        raise ServiceError("INVALID_ASSET", "Invalid asset ID", 422) from exc
    if (
        asset is None
        or asset.kind != kind
        or asset.document_id != document.id
        or asset.document_version != document.current_version
    ):
        raise ServiceError(
            "INVALID_ASSET", "Asset does not match the document, version and kind", 409
        )
    return asset.id


def edit_question(session, question, payload, user):
    check_revision(question, payload.expected_revision)
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if not changes:
        return review_view(session, question)
    if "text" in changes:
        question.question_text = payload.text
    if "difficulty" in changes:
        question.difficulty = payload.difficulty
    old_subject = question.subject_id
    if payload.subject is not None:
        question.subject = DataService._get_or_create_subject(session, payload.subject)
    if question.subject is None:
        raise ServiceError("SUBJECT_REQUIRED", "Set a subject before editing this question", 422)
    # A subject change must never retain module/topic links from another subject.
    changed_subject = question.subject.id != old_subject
    if changed_subject:
        question.module = None
        question.topics.clear()
    if "module" in changes:
        question.module = (
            DataService._get_or_create_module(session, question.subject, payload.module)
            if payload.module
            else None
        )
    if "topic" in changes or "topics" in changes:
        question.topics.clear()
        session.flush()
        names = (payload.topics or []) if "topics" in changes else ([payload.topic] if payload.topic else [])
        for name in names:
            topic = DataService._get_or_create_topic(session, question.subject, name)
            question.topics.append(QuestionTopic(topic=topic, assigned_by="manual"))
    if "question_asset_id" in changes:
        question.question_asset_id = validated_asset(
            session, payload.question_asset_id, "question_image", question.document
        )
    answer_fields = {"official_solution", "solution_document_id", "solution_asset_id"}
    if answer_fields & changes.keys():
        answer = first_answer(session, question)
        if answer is None:
            answer = Answer(
                question=question,
                answer_text="",
                answer_type="reviewed",
                review_status="pending_review",
            )
            session.add(answer)
        if "official_solution" in changes:
            answer.answer_text = payload.official_solution or ""
        if "solution_document_id" in changes:
            from app.data_service.uploads import get_document

            source = (
                get_document(session, payload.solution_document_id)
                if payload.solution_document_id
                else None
            )
            if source and source.document_type != "answer_sheet":
                raise ServiceError(
                    "INVALID_SOLUTION_SOURCE", "Choose an answer sheet as the solution source", 422
                )
            answer.source_document_id = source.id if source else None
            answer.solution_asset_id = None
        if "solution_asset_id" in changes:
            source = (
                session.get(Document, answer.source_document_id)
                if answer.source_document_id
                else question.document
            )
            answer.solution_asset_id = validated_asset(
                session, payload.solution_asset_id, "solution_image", source
            )
        answer.review_status = "pending_review"
    question.status = "pending_review"
    for existing_answer in session.scalars(select(Answer).where(Answer.question_id == question.id)):
        existing_answer.review_status = "pending_review"
    question.revision += 1
    invalidate_index(session, question)
    audit(
        session,
        user,
        "question_edited",
        "question",
        question.external_id,
        fields=sorted(changes),
        revision=question.revision,
    )
    session.flush()
    return review_view(session, question)


def review_question(session, question, payload, user, model):
    check_revision(question, payload.expected_revision)
    if payload.status == "approved" and question.subject is None:
        raise ServiceError("SUBJECT_REQUIRED", "Assign a subject before approving", 422)
    if payload.status == "approved" and not question.document.source_type:
        raise ServiceError(
            "SOURCE_TYPE_REQUIRED", "Set the document source type before approving", 422
        )
    question.status = payload.status
    question.flag_note = payload.note if payload.flagged else None
    question.revision += 1
    answer = first_answer(session, question)
    if payload.approve_solution and payload.status != "approved":
        raise ServiceError(
            "INVALID_REVIEW", "Solutions can be approved only with an approved question", 422
        )
    if payload.approve_solution and answer:
        if not answer.answer_text and answer.solution_asset_id is None:
            raise ServiceError(
                "EMPTY_SOLUTION", "Provide text or an image before approving a solution", 422
            )
        answer.review_status = "approved"
    invalidate_index(session, question)
    if question.status == "approved":
        queue_index(session, question, model)
    audit(
        session,
        user,
        "question_reviewed",
        "question",
        question.external_id,
        status=payload.status,
        note=payload.note,
        revision=question.revision,
        approve_solution=payload.approve_solution,
    )
    session.flush()
    return review_view(session, question)


def asset_links(session, question, storage):
    from app.domain.management import AssetLinks

    answer = session.scalar(
        select(Answer)
        .where(
            Answer.question_id == question.id,
            Answer.review_status == "approved",
        )
        .order_by(Answer.created_at, Answer.id)
        .limit(1)
    )
    image = (
        session.get(ContentAsset, question.question_asset_id)
        if question.question_asset_id
        else None
    )
    solution = (
        session.get(ContentAsset, answer.solution_asset_id)
        if answer and answer.solution_asset_id
        else None
    )
    source = (
        session.get(Document, answer.source_document_id)
        if answer and answer.source_document_id
        else None
    )
    return AssetLinks(
        question_id=question.external_id,
        question_image_url=storage.download_url(image.object_key) if image else None,
        solution_image_url=storage.download_url(solution.object_key) if solution else None,
        solution_document_id=source.external_id if source else None,
        expires_in_seconds=storage.settings.signed_url_expiry_seconds,
    )
