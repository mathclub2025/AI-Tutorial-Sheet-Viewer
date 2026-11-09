"""Opt-in real PostgreSQL test; use an isolated test database with pgvector installed."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text

from app.data_service.semantic import semantic_search
from app.data_service.settings import DataServiceSettings
from app.data_service.worker import Worker
from app.domain.management import SemanticSearchRequest
from app.persistence.database import create_session_factory, session_scope
from app.persistence.models import (
    Document,
    IntegrationTask,
    QuestionEmbedding,
    QuestionRecord,
    Subject,
)


@pytest.mark.skipif(
    not os.environ.get("MATHCLUB_TEST_DATABASE_URL"),
    reason="Set MATHCLUB_TEST_DATABASE_URL to run PostgreSQL/pgvector migration and locking checks",
)
def test_postgres_migration_preserves_rows_vector_search_and_queue_claims():
    engine = create_engine(os.environ["MATHCLUB_TEST_DATABASE_URL"])
    schema = "mathclub_test_" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = create_engine(
        os.environ["MATHCLUB_TEST_DATABASE_URL"],
        connect_args={"options": f"-csearch_path={schema},public"},
    )
    try:
        # Upgrade a real v0.2 database with an existing document.
        cfg = Config("alembic.ini")
        with test_engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "ec27961bf9a9")
        factory = create_session_factory(test_engine)
        with session_scope(factory) as session:
            document = Document(
                external_id="existing-doc",
                title="Existing document",
                document_type="tutorial_sheet",
                source_type="tutorial",
                original_filename="old.pdf",
                object_key="documents/old/paper.pdf",
                bucket_name="private",
                mime_type="application/pdf",
                file_size_bytes=10,
                visibility="public",
            )
            session.add(document)
        with test_engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
        with session_scope(factory) as session:
            assert session.scalar(select(func.count()).select_from(Document)) == 1
            document = session.scalar(select(Document))
            subject = Subject(name="Math")
            session.add(subject)
            question = QuestionRecord(
                external_id="vector-q",
                document=document,
                subject=subject,
                question_text="Differentiate x squared",
                status="approved",
            )
            session.add(question)
            session.flush()
            session.add(
                QuestionEmbedding(
                    question_id=question.id,
                    embedding=[1, 0, 0],
                    model_name="test",
                    content_revision=question.revision,
                )
            )
            for index in range(2):
                session.add(
                    IntegrationTask(
                        dedupe_key=f"test-{index}",
                        kind="index",
                        payload={"question_id": "vector-q", "revision": 1, "model": "test"},
                    )
                )
        config = DataServiceSettings(_env_file=None, embedding_model="test", embedding_dimensions=3)

        class Embeddings:
            def embed(self, texts):
                return [[1, 0, 0]]

        with session_scope(factory) as session:
            result = semantic_search(
                session, SemanticSearchRequest(query="derivative"), Embeddings(), config
            )
            assert result.items[0].question.id == "vector-q"
        worker = Worker(factory, config, embeddings=Embeddings())
        first, second = worker._claim(), worker._claim()
        assert first[0] != second[0]
        assert worker._claim() is None
    finally:
        test_engine.dispose()
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
