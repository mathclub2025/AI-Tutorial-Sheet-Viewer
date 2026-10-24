from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="uploader")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    uploaded_documents: Mapped[list["Document"]] = relationship(back_populates="uploader")

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'reviewer', 'uploader')", name="ck_users_role"),
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (Index("uq_subjects_name_lower", text("lower(name)"), unique=True),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    modules: Mapped[list["Module"]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )
    topics: Mapped[list["Topic"]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )


class Module(Base):
    __tablename__ = "modules"
    __table_args__ = (
        UniqueConstraint("subject_id", "module_number", name="uq_modules_subject_number"),
        UniqueConstraint("subject_id", "name", name="uq_modules_subject_name"),
        CheckConstraint(
            "module_number IS NULL OR module_number > 0", name="ck_modules_positive_number"
        ),
        Index(
            "uq_modules_subject_name_lower",
            "subject_id",
            text("lower(name)"),
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    module_number: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)

    subject: Mapped[Subject] = relationship(back_populates="modules")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('question_paper', 'answer_sheet', 'tutorial_sheet', 'other')",
            name="ck_documents_type",
        ),
        CheckConstraint(
            "source_type IS NULL OR source_type IN ('tutorial', 'pyq', 'practice')",
            name="ck_documents_source_type",
        ),
        CheckConstraint(
            "processing_status IN ('pending', 'processing', 'succeeded', 'failed')",
            name="ck_documents_processing_status",
        ),
        CheckConstraint(
            "visibility IN ('private', 'public')",
            name="ck_documents_visibility",
        ),
        CheckConstraint(
            "publication_year IS NULL OR publication_year BETWEEN 1990 AND 2100",
            name="ck_documents_publication_year",
        ),
        CheckConstraint(
            "indexing_status IN ('pending', 'queued', 'indexed', 'failed')",
            name="ck_documents_indexing_status",
        ),
        CheckConstraint("file_size_bytes > 0", name="ck_documents_positive_size"),
        UniqueConstraint("external_id", name="uq_documents_external_id"),
        UniqueConstraint("object_key", name="uq_documents_object_key"),
        Index("ix_documents_subject_module_visibility", "subject_id", "module_id", "visibility"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    current_version: Mapped[str] = mapped_column(
        String(100), nullable=False, default="v1", server_default="v1"
    )
    publication_year: Mapped[int | None] = mapped_column(Integer)
    subject_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), index=True
    )
    module_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("modules.id", ondelete="SET NULL"), index=True
    )
    uploaded_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(24))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    bucket_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    processing_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    indexing_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="private")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    uploader: Mapped[User | None] = relationship(back_populates="uploaded_documents")
    subject: Mapped[Subject | None] = relationship()
    module: Mapped[Module | None] = relationship()
    questions: Mapped[list["QuestionRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    processing_jobs: Mapped[list["DocumentProcessingJob"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class QuestionRecord(Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'pending_review', 'approved', 'rejected', 'archived')",
            name="ck_questions_status",
        ),
        CheckConstraint("page_start IS NULL OR page_start > 0", name="ck_questions_page_start"),
        CheckConstraint(
            "page_end IS NULL OR page_end >= page_start", name="ck_questions_page_range"
        ),
        CheckConstraint("marks IS NULL OR marks >= 0", name="ck_questions_nonnegative_marks"),
        UniqueConstraint(
            "processing_job_id",
            "extraction_id",
            name="uq_questions_job_extraction",
        ),
        Index("ix_questions_status_document", "status", "document_id"),
        Index("ix_questions_status_subject", "status", "subject_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL", name="fk_questions_subject_id_subjects"),
        index=True,
    )
    module_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("modules.id", ondelete="SET NULL", name="fk_questions_module_id_modules"),
        index=True,
    )
    document_version: Mapped[str | None] = mapped_column(String(100))
    extraction_id: Mapped[str | None] = mapped_column(String(128))
    processing_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "document_processing_jobs.id",
            ondelete="SET NULL",
            name="fk_questions_processing_job_id_document_processing_jobs",
        ),
        index=True,
    )
    question_number: Mapped[str | None] = mapped_column(String(100))
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str | None] = mapped_column(String(64))
    marks: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    document: Mapped[Document] = relationship(back_populates="questions")
    subject: Mapped[Subject | None] = relationship()
    module: Mapped[Module | None] = relationship()
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    topics: Mapped[list["QuestionTopic"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    embedding: Mapped["QuestionEmbedding | None"] = relationship(
        back_populates="question", cascade="all, delete-orphan", uselist=False
    )


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('draft', 'pending_review', 'approved', 'rejected', 'archived')",
            name="ck_answers_review_status",
        ),
        CheckConstraint("page_start IS NULL OR page_start > 0", name="ck_answers_page_start"),
        CheckConstraint("page_end IS NULL OR page_end >= page_start", name="ck_answers_page_range"),
        UniqueConstraint("external_id", name="uq_answers_external_id"),
        Index("ix_answers_question_review", "question_id", "review_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(128))
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_type: Mapped[str | None] = mapped_column(String(64))
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    question: Mapped[QuestionRecord] = relationship(back_populates="answers")


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        Index(
            "uq_topics_root_name",
            "subject_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("parent_topic_id IS NULL"),
        ),
        Index(
            "uq_topics_child_name",
            "subject_id",
            "parent_topic_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("parent_topic_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_topic_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    subject: Mapped[Subject] = relationship(back_populates="topics")
    parent: Mapped["Topic | None"] = relationship(remote_side="Topic.id", back_populates="children")
    children: Mapped[list["Topic"]] = relationship(back_populates="parent")
    questions: Mapped[list["QuestionTopic"]] = relationship(back_populates="topic")


class QuestionTopic(Base):
    __tablename__ = "question_topics"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_question_topics_confidence",
        ),
        CheckConstraint("assigned_by IN ('manual', 'ai')", name="ck_question_topics_assigned_by"),
    )

    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    assigned_by: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")

    question: Mapped[QuestionRecord] = relationship(back_populates="topics")
    topic: Mapped[Topic] = relationship(back_populates="questions")


class DocumentProcessingJob(Base):
    __tablename__ = "document_processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('extraction', 'ocr', 'indexing')", name="ck_processing_jobs_type"
        ),
        CheckConstraint(
            "source_type IS NULL OR source_type IN ('tutorial', 'pyq', 'practice')",
            name="ck_processing_jobs_source_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_processing_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_processing_jobs_attempts"),
        UniqueConstraint("client_job_key", name="uq_processing_jobs_client_key"),
        UniqueConstraint("ai_job_id", name="uq_processing_jobs_ai_job_id"),
        Index("ix_processing_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(String(24), nullable=False)
    client_job_key: Mapped[str] = mapped_column(String(128), nullable=False)
    document_version: Mapped[str] = mapped_column(
        String(100), nullable=False, default="v1", server_default="v1"
    )
    source_type: Mapped[str | None] = mapped_column(String(24))
    ai_job_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(2000))
    result_sha256: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_DOCUMENT, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="processing_jobs")


class QueryEventRecord(Base):
    __tablename__ = "query_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('search', 'ask', 'explain')", name="ck_query_events_type"),
        Index("ix_query_events_created_at", "created_at"),
    )

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    query: Mapped[str | None] = mapped_column(Text)
    question_id: Mapped[str | None] = mapped_column(String(128))
    filters: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    result_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class DocumentResultReceipt(Base):
    __tablename__ = "document_result_events"
    __table_args__ = (
        CheckConstraint(
            "indexing_status IN ('pending', 'queued', 'indexed', 'not_applicable')",
            name="ck_document_result_events_indexing_status",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    job_id: Mapped[str] = mapped_column(String(128), nullable=False)
    document_id: Mapped[str] = mapped_column(String(128), nullable=False)
    document_version: Mapped[str] = mapped_column(String(100), nullable=False)
    indexing_status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class QuestionEmbedding(Base):
    __tablename__ = "question_embeddings"

    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    question: Mapped[QuestionRecord] = relationship(back_populates="embedding")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
