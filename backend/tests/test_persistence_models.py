from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.persistence.database import create_database_engine, create_session_factory, session_scope
from app.persistence.models import (
    Answer,
    Base,
    Document,
    DocumentProcessingJob,
    QuestionRecord,
    Subject,
    User,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_persistence_schema_and_relationships(session):
    subject = Subject(name="Mathematics")
    user = User(name="Admin", email="admin@example.edu", password_hash="argon2id-hash")
    document = Document(
        external_id="doc-29",
        title="Calculus paper",
        document_type="question_paper",
        original_filename="calculus.pdf",
        object_key=f"documents/{uuid4()}/paper.pdf",
        bucket_name="mathclub-private",
        mime_type="application/pdf",
        file_size_bytes=1200,
        uploader=user,
        subject=subject,
    )
    question = QuestionRecord(
        external_id="q-29-1",
        document=document,
        question_text="Differentiate x squared",
        status="approved",
    )
    answer = Answer(question=question, answer_text="2x", review_status="approved")
    session.add_all([user, subject, document, question, answer])
    session.commit()

    saved = session.scalar(select(QuestionRecord).where(QuestionRecord.external_id == "q-29-1"))
    assert saved is not None
    assert saved.document.external_id == "doc-29"
    assert saved.answers[0].answer_text == "2x"
    assert session.scalar(select(User).where(User.email == "admin@example.edu")) is not None


def test_duplicate_object_keys_and_invalid_question_status_are_rejected(session):
    shared_key = f"documents/{uuid4()}/paper.pdf"
    for external_id in ("doc-1", "doc-2"):
        session.add(
            Document(
                external_id=external_id,
                title="Test",
                document_type="question_paper",
                original_filename="paper.pdf",
                object_key=shared_key,
                bucket_name="private",
                mime_type="application/pdf",
                file_size_bytes=1,
            )
        )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    document = Document(
        external_id="doc-3",
        title="Test",
        document_type="question_paper",
        original_filename="paper.pdf",
        object_key=f"documents/{uuid4()}/paper.pdf",
        bucket_name="private",
        mime_type="application/pdf",
        file_size_bytes=1,
    )
    session.add(document)
    session.flush()
    session.add(
        QuestionRecord(
            external_id="q-3",
            document=document,
            question_text="Invalid state test",
            status="published",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_processing_job_client_key_is_idempotent(session):
    document = Document(
        external_id="job-doc",
        title="Test",
        document_type="question_paper",
        source_type="pyq",
        original_filename="paper.pdf",
        object_key=f"documents/{uuid4()}/paper.pdf",
        bucket_name="private",
        mime_type="application/pdf",
        file_size_bytes=1,
    )
    session.add(document)
    session.flush()
    session.add_all(
        [
            DocumentProcessingJob(
                document=document,
                job_type="extraction",
                client_job_key="job-key-unique-1",
            ),
            DocumentProcessingJob(
                document=document,
                job_type="extraction",
                client_job_key="job-key-unique-1",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_email_is_unique_case_insensitively(session):
    session.add_all(
        [
            User(name="One", email="Admin@example.edu", password_hash="hash"),
            User(name="Two", email="admin@example.edu", password_hash="hash"),
        ]
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_session_scope_commits_and_rolls_back_transactions():
    engine = create_database_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with session_scope(factory) as db:
        db.add(User(name="Committed", email="saved@example.edu", password_hash="hash"))

    with pytest.raises(RuntimeError, match="rollback"):
        with session_scope(factory) as db:
            db.add(User(name="Discarded", email="discard@example.edu", password_hash="hash"))
            raise RuntimeError("rollback")

    with factory() as db:
        assert db.scalar(select(User.email).where(User.email == "saved@example.edu"))
        assert db.scalar(select(User.email).where(User.email == "discard@example.edu")) is None
    engine.dispose()
