from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ServiceError
from app.domain.models import (
    DocumentResultAck,
    DocumentResultEvent,
    FilterCatalog,
    QueryEvent,
    Question,
    SearchEnvelope,
    SearchFilters,
    SearchHit,
    SearchRequest,
    SourceReference,
)
from app.persistence.models import (
    Answer,
    Document,
    DocumentProcessingJob,
    DocumentResultReceipt,
    Module,
    QueryEventRecord,
    QuestionRecord,
    QuestionTopic,
    Subject,
    Topic,
)


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _safe_like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _lock_idempotency_key(session: Session, value: str) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        lock_id = int.from_bytes(sha256(value.encode()).digest()[:8], byteorder="big", signed=True)
        session.execute(select(func.pg_advisory_xact_lock(lock_id)))


def _normalized_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class DataService:
    def record_query_event(self, session: Session, event: QueryEvent) -> None:
        _lock_idempotency_key(session, f"query-event:{event.event_id}")
        existing = session.get(QueryEventRecord, event.event_id)
        stored_fields = (
            "timestamp",
            "event_type",
            "query",
            "question_id",
            "filters",
            "result_count",
        )
        if existing is not None:
            expected = event.model_dump()
            actual = {field: getattr(existing, field) for field in stored_fields}
            expected_fields = {field: expected[field] for field in stored_fields}
            actual["timestamp"] = _normalized_datetime(actual["timestamp"])
            expected_fields["timestamp"] = _normalized_datetime(expected_fields["timestamp"])
            if actual != expected_fields:
                raise ServiceError(
                    "EVENT_ID_CONFLICT", "Event ID was reused with different content", 409
                )
            return
        filters = event.filters.model_dump(mode="json") if event.filters is not None else None
        session.add(
            QueryEventRecord(
                event_id=event.event_id,
                timestamp=event.timestamp,
                event_type=event.event_type,
                request_id=event.request_id,
                query=event.query,
                question_id=event.question_id,
                filters=filters,
                result_count=event.result_count,
            )
        )
        session.flush()

    def _question_query(self, filters: SearchFilters | None = None):
        statement = (
            select(QuestionRecord)
            .join(QuestionRecord.document)
            .options(
                selectinload(QuestionRecord.subject),
                selectinload(QuestionRecord.module),
                selectinload(QuestionRecord.topics).selectinload(QuestionTopic.topic),
            )
            .where(
                QuestionRecord.status == "approved",
                QuestionRecord.subject_id.is_not(None),
                Document.visibility == "public",
                Document.source_type.is_not(None),
            )
        )
        if filters is not None:
            if filters.subject:
                statement = statement.join(QuestionRecord.subject).where(
                    func.lower(Subject.name) == filters.subject.lower()
                )
            if filters.module:
                statement = statement.join(QuestionRecord.module).where(
                    func.lower(Module.name) == filters.module.lower()
                )
            if filters.topic:
                statement = statement.where(
                    QuestionRecord.topics.any(
                        QuestionTopic.topic.has(func.lower(Topic.name) == filters.topic.lower())
                    )
                )
            if filters.year is not None:
                statement = statement.where(Document.publication_year == filters.year)
            if filters.source_type is not None:
                statement = statement.where(Document.source_type == filters.source_type.value)
        return statement

    def search(self, session: Session, request: SearchRequest) -> SearchEnvelope:
        words = list(
            dict.fromkeys(re.findall(r"[^\W_]+", request.query.lower(), flags=re.UNICODE))
        )[:32]
        if not words:
            return SearchEnvelope(items=[])
        any_word = or_(
            *[
                or_(
                    QuestionRecord.question_text.ilike(_safe_like_pattern(word), escape="\\"),
                    select(Answer.id)
                    .where(
                        Answer.question_id == QuestionRecord.id,
                        Answer.review_status == "approved",
                        Answer.answer_text.ilike(_safe_like_pattern(word), escape="\\"),
                    )
                    .exists(),
                )
                for word in words
            ]
        )
        candidates = (
            session.scalars(
                self._question_query(request.filters)
                .where(any_word)
                .order_by(QuestionRecord.external_id)
                .limit(500)
            )
            .unique()
            .all()
        )
        ranked = []
        for question in candidates:
            searchable = question.question_text.lower()
            approved_answers = session.scalars(
                select(Answer.answer_text).where(
                    Answer.question_id == question.id, Answer.review_status == "approved"
                )
            ).all()
            searchable += " " + " ".join(approved_answers).lower()
            matches = sum(word in searchable for word in words)
            score = matches / len(words)
            ranked.append((score, question))
        ranked.sort(key=lambda item: (-item[0], item[1].external_id))
        return SearchEnvelope(
            items=[
                SearchHit(question=self._to_question(session, row), relevance_score=score)
                for score, row in ranked[: request.limit]
            ]
        )

    def similar(self, session: Session, question_id: str, limit: int) -> SearchEnvelope:
        selected = session.scalar(
            self._question_query().where(QuestionRecord.external_id == question_id)
        )
        if selected is None:
            raise ServiceError("QUESTION_NOT_FOUND", "Question was not found", 404)
        selected_words = set(
            re.findall(r"[^\W_]+", selected.question_text.lower(), flags=re.UNICODE)
        )
        candidates = (
            session.scalars(
                self._question_query()
                .where(QuestionRecord.id != selected.id)
                .order_by(QuestionRecord.external_id)
                .limit(500)
            )
            .unique()
            .all()
        )
        ranked = []
        for row in candidates:
            words = set(re.findall(r"[^\W_]+", row.question_text.lower(), flags=re.UNICODE))
            union = selected_words | words
            score = len(selected_words & words) / len(union) if union else 0.0
            if score > 0:
                ranked.append((score, row))
        ranked.sort(key=lambda item: (-item[0], item[1].external_id))
        return SearchEnvelope(
            items=[
                SearchHit(question=self._to_question(session, row), relevance_score=score)
                for score, row in ranked[:limit]
            ]
        )

    def get_question(self, session: Session, question_id: str) -> Question:
        row = session.scalar(
            self._question_query().where(QuestionRecord.external_id == question_id)
        )
        if row is None:
            raise ServiceError("QUESTION_NOT_FOUND", "Question was not found", 404)
        return self._to_question(session, row)

    def catalog(self, session: Session) -> FilterCatalog:
        rows = session.execute(
            select(
                Subject.name,
                Module.name,
                Topic.name,
                Document.publication_year,
                Document.source_type,
            )
            .select_from(QuestionRecord)
            .join(QuestionRecord.document)
            .join(QuestionRecord.subject)
            .outerjoin(QuestionRecord.module)
            .outerjoin(QuestionRecord.topics)
            .outerjoin(QuestionTopic.topic)
            .where(QuestionRecord.status == "approved", Document.visibility == "public")
            .where(
                QuestionRecord.subject_id.is_not(None),
                Document.source_type.is_not(None),
            )
            .distinct()
            .limit(5000)
        ).all()
        combinations = [
            SearchFilters(
                subject=subject,
                module=module,
                topic=topic,
                year=year,
                source_type=source_type,
            )
            for subject, module, topic, year, source_type in rows
        ]
        combinations.sort(
            key=lambda item: (
                item.subject or "",
                item.module or "",
                item.topic or "",
                item.year or 0,
                item.source_type.value if item.source_type else "",
            )
        )
        return FilterCatalog(combinations=combinations)

    def accept_document_result(
        self, session: Session, event: DocumentResultEvent
    ) -> DocumentResultAck:
        _lock_idempotency_key(session, f"document-result:{event.event_id}")
        event_content = event.model_dump(mode="json", exclude={"request_id"})
        event_digest = sha256(_canonical_json(event_content).encode()).hexdigest()
        receipt = session.get(DocumentResultReceipt, event.event_id)
        if receipt is not None:
            if receipt.content_sha256 != event_digest:
                raise ServiceError(
                    "EVENT_ID_CONFLICT", "Result event ID was reused with different content", 409
                )
            return self._result_ack(receipt)

        document = session.scalar(
            select(Document).where(Document.external_id == event.document_id).with_for_update()
        )
        if document is None:
            raise ServiceError("DOCUMENT_NOT_FOUND", "Document was not found", 404)
        if (
            document.current_version != event.document_version
            or document.source_type != event.source_type.value
        ):
            raise ServiceError(
                "DOCUMENT_VERSION_CONFLICT",
                "Result does not match the current document version and source type",
                409,
            )

        job_digest_payload = event.model_dump(mode="json", exclude={"request_id", "event_id"})
        job_digest = sha256(_canonical_json(job_digest_payload).encode()).hexdigest()
        job = session.scalar(
            select(DocumentProcessingJob)
            .where(DocumentProcessingJob.client_job_key == event.client_job_key)
            .with_for_update()
        )
        if job is None:
            job = DocumentProcessingJob(
                document_id=document.id,
                job_type="extraction",
                client_job_key=event.client_job_key,
                document_version=event.document_version,
                source_type=event.source_type.value,
                ai_job_id=event.job_id,
                status="queued",
                attempts=1,
                metadata_json={},
            )
            session.add(job)
            session.flush()
        elif (
            job.document_id != document.id
            or job.document_version != event.document_version
            or job.source_type not in (None, event.source_type.value)
            or (job.ai_job_id is not None and job.ai_job_id != event.job_id)
        ):
            raise ServiceError(
                "JOB_IDENTITY_CONFLICT", "Processing job identity does not match", 409
            )
        if job.result_sha256 is not None and job.result_sha256 != job_digest:
            raise ServiceError(
                "JOB_RESULT_CONFLICT", "A different terminal result was already accepted", 409
            )

        now = datetime.now(timezone.utc)
        job.ai_job_id = event.job_id
        job.result_sha256 = job_digest
        job.started_at = job.started_at or now
        job.finished_at = now
        job.status = "succeeded" if event.status == "completed" else "failed"
        job.error_message = event.error.message if event.error else None
        if event.status == "completed":
            for extracted in event.questions:
                subject = self._get_or_create_subject(session, extracted.subject)
                module = (
                    self._get_or_create_module(session, subject, extracted.module)
                    if extracted.module
                    else None
                )
                canonical_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        ":".join(
                            (
                                event.document_id,
                                event.document_version,
                                event.job_id,
                                extracted.extraction_id,
                            )
                        ),
                    )
                )
                question = session.scalar(
                    select(QuestionRecord).where(
                        QuestionRecord.processing_job_id == job.id,
                        QuestionRecord.extraction_id == extracted.extraction_id,
                    )
                )
                values = {
                    "external_id": canonical_id,
                    "document": document,
                    "subject": subject,
                    "module": module,
                    "document_version": event.document_version,
                    "extraction_id": extracted.extraction_id,
                    "processing_job_id": job.id,
                    "question_number": extracted.source.question_number,
                    "question_text": extracted.text,
                    "page_start": extracted.source.page_number,
                    "page_end": extracted.source.page_number,
                    "status": "pending_review",
                }
                if question is None:
                    question = QuestionRecord(**values)
                    session.add(question)
                    session.flush()
                else:
                    for name, value in values.items():
                        if name != "external_id":
                            setattr(question, name, value)
                if extracted.topic:
                    topic = self._get_or_create_topic(session, subject, extracted.topic)
                    assignment = session.get(QuestionTopic, (question.id, topic.id))
                    if assignment is None:
                        session.add(
                            QuestionTopic(
                                question_id=question.id,
                                topic_id=topic.id,
                                confidence=extracted.confidence,
                                assigned_by="ai",
                            )
                        )
                if extracted.official_solution is not None:
                    answer_id = f"{canonical_id}.answer"
                    answer = session.scalar(select(Answer).where(Answer.external_id == answer_id))
                    if answer is None:
                        answer = Answer(
                            external_id=answer_id,
                            question=question,
                            answer_text=extracted.official_solution,
                            answer_type="extracted",
                            review_status="pending_review",
                        )
                        session.add(answer)
                    else:
                        answer.answer_text = extracted.official_solution
                        answer.review_status = "pending_review"
            document.processing_status = "succeeded"
            document.indexing_status = "pending"
            indexing_status = "pending"
        else:
            document.processing_status = "failed"
            indexing_status = "not_applicable"

        session.add(
            DocumentResultReceipt(
                event_id=event.event_id,
                content_sha256=event_digest,
                job_id=event.job_id,
                document_id=event.document_id,
                document_version=event.document_version,
                indexing_status=indexing_status,
            )
        )
        session.flush()
        return DocumentResultAck(
            accepted=True,
            event_id=event.event_id,
            job_id=event.job_id,
            document_id=event.document_id,
            document_version=event.document_version,
            indexing_status=indexing_status,
        )

    @staticmethod
    def _result_ack(receipt: DocumentResultReceipt) -> DocumentResultAck:
        return DocumentResultAck(
            accepted=True,
            event_id=receipt.event_id,
            job_id=receipt.job_id,
            document_id=receipt.document_id,
            document_version=receipt.document_version,
            indexing_status=receipt.indexing_status,
        )

    @staticmethod
    def _get_or_create_subject(session: Session, name: str) -> Subject:
        _lock_idempotency_key(session, f"subject:{name.casefold()}")
        subject = session.scalar(select(Subject).where(func.lower(Subject.name) == name.lower()))
        if subject is None:
            subject = Subject(name=name)
            session.add(subject)
            session.flush()
        return subject

    @staticmethod
    def _get_or_create_module(session: Session, subject: Subject, name: str) -> Module:
        _lock_idempotency_key(session, f"module:{subject.id}:{name.casefold()}")
        module = session.scalar(
            select(Module).where(
                Module.subject_id == subject.id, func.lower(Module.name) == name.lower()
            )
        )
        if module is None:
            module = Module(subject_id=subject.id, name=name, module_number=None)
            session.add(module)
            session.flush()
        return module

    @staticmethod
    def _get_or_create_topic(session: Session, subject: Subject, name: str) -> Topic:
        _lock_idempotency_key(session, f"topic:{subject.id}:{name.casefold()}")
        topic = session.scalar(
            select(Topic).where(
                Topic.subject_id == subject.id,
                Topic.parent_topic_id.is_(None),
                func.lower(Topic.name) == name.lower(),
            )
        )
        if topic is None:
            topic = Topic(subject_id=subject.id, name=name)
            session.add(topic)
            session.flush()
        return topic

    @staticmethod
    def _to_question(session: Session, row: QuestionRecord) -> Question:
        document = row.document
        topic_assignments = sorted(
            row.topics,
            key=lambda assignment: (
                assignment.assigned_by != "manual",
                -(assignment.confidence or 0),
                assignment.topic.name.casefold(),
            ),
        )
        topic = topic_assignments[0].topic if topic_assignments else None
        answer = session.scalar(
            select(Answer)
            .where(Answer.question_id == row.id, Answer.review_status == "approved")
            .order_by(Answer.created_at, Answer.id)
            .limit(1)
        )
        source = SourceReference(
            source_type=document.source_type,
            document_id=document.external_id,
            document_title=document.title,
            page_number=row.page_start,
            question_number=row.question_number,
            year=document.publication_year,
        )
        return Question(
            id=row.external_id,
            text=row.question_text,
            subject=row.subject.name if row.subject else "",
            module=row.module.name if row.module else None,
            topic=topic.name if topic else None,
            source=source,
            official_solution=answer.answer_text if answer else None,
        )
