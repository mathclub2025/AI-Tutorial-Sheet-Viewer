import pytest
from sqlalchemy import create_engine

from app.data_service.semantic import chunk_query, semantic_search
from app.data_service.settings import DataServiceSettings
from app.domain.management import SemanticSearchRequest
from app.persistence.database import create_session_factory, session_scope
from app.persistence.models import (
    Base,
    Document,
    QuestionEmbedding,
    QuestionRecord,
    Subject,
)

VECTORS = {
    "variance": [1, 0.2, 0],
    "bayes": [0.2, 1, 0],
    "mixed": [1, 1, 0],
    "poisson": [0.1, 0.1, 1],
}


class FakeEmbeddings:
    def embed(self, texts):
        return [VECTORS[text.rstrip(".?!")] for text in texts]


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "semantic.db"), connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def seed(session, entries):
    subject = Subject(name="Math")
    session.add(subject)
    session.flush()
    document = Document(
        external_id="doc",
        title="Doc",
        document_type="tutorial_sheet",
        source_type="tutorial",
        original_filename="doc.json",
        object_key="imported/doc.json",
        bucket_name="local-import",
        mime_type="application/json",
        file_size_bytes=10,
        visibility="public",
    )
    session.add(document)
    session.flush()
    for entry in entries:
        question = QuestionRecord(
            external_id=entry["external_id"],
            document=document,
            subject=subject,
            question_text=entry["text"],
            status="approved",
        )
        session.add(question)
        session.flush()
        session.add(
            QuestionEmbedding(
                question_id=question.id,
                embedding=entry["vector"],
                model_name=entry.get("model", "t"),
                content_revision=question.revision + entry.get("revision_offset", 0),
            )
        )


def config():
    return DataServiceSettings(_env_file=None, embedding_model="t", embedding_dimensions=3)


def test_short_queries_remain_a_single_chunk():
    assert chunk_query("find the median") == ["find the median"]


def test_sentence_splitting_discards_empty_chunks():
    assert chunk_query("variance. \n\n bayes? poisson!  ") == [
        "variance.",
        "bayes?",
        "poisson!",
    ]


def test_chunks_are_capped_at_eight():
    query = ". ".join(f"sentence {index}" for index in range(12))
    chunks = chunk_query(query)
    assert len(chunks) == 8
    assert chunks[0] == "sentence 0."
    assert chunks[-1] == "sentence 7."


def test_blank_queries_produce_no_chunks():
    assert chunk_query("   ") == []


def test_multi_chunk_search_merges_deduplicates_and_ranks(factory):
    with session_scope(factory) as session:
        seed(
            session,
            [
                {"external_id": "q-a", "text": "variance question", "vector": [1, 0, 0]},
                {"external_id": "q-b", "text": "bayes question", "vector": [0, 1, 0]},
                {"external_id": "q-c", "text": "mixed components", "vector": [0.9, 0.9, 0]},
            ],
        )
    with session_scope(factory) as session:
        result = semantic_search(
            session,
            SemanticSearchRequest(query="variance. bayes. mixed"),
            FakeEmbeddings(),
            config(),
        )
    hits = result.items
    assert [hit.question.id for hit in hits] == ["q-c", "q-a", "q-b"]
    assert hits[0].relevance_score == pytest.approx(1.0)
    assert hits[1].relevance_score == pytest.approx(0.98058, abs=1e-4)
    assert hits[2].relevance_score == pytest.approx(0.98058, abs=1e-4)


def test_search_excludes_other_models_and_stale_revisions(factory):
    with session_scope(factory) as session:
        seed(
            session,
            [
                {"external_id": "q-a", "text": "variance question", "vector": [1, 0, 0]},
                {"external_id": "q-b", "text": "variance other model", "vector": [1, 0, 0], "model": "other"},
                {
                    "external_id": "q-c",
                    "text": "variance stale revision",
                    "vector": [1, 0, 0],
                    "revision_offset": -1,
                },
            ],
        )
    with session_scope(factory) as session:
        result = semantic_search(
            session, SemanticSearchRequest(query="variance"), FakeEmbeddings(), config()
        )
    assert [hit.question.id for hit in result.items] == ["q-a"]


def test_search_applies_requested_filters(factory):
    with session_scope(factory) as session:
        seed(session, [{"external_id": "q-a", "text": "variance question", "vector": [1, 0, 0]}])
    with session_scope(factory) as session:
        result = semantic_search(
            session,
            SemanticSearchRequest(query="variance", filters={"subject": "Math"}),
            FakeEmbeddings(),
            config(),
        )
        assert [hit.question.id for hit in result.items] == ["q-a"]
        empty = semantic_search(
            session,
            SemanticSearchRequest(query="variance", filters={"subject": "Physics"}),
            FakeEmbeddings(),
            config(),
        )
    assert empty.items == []


def test_result_limit_is_enforced(factory):
    with session_scope(factory) as session:
        seed(
            session,
            [
                {"external_id": f"q-{index}", "text": "variance question", "vector": [1, 0, 0]}
                for index in range(3)
            ],
        )
    with session_scope(factory) as session:
        result = semantic_search(
            session,
            SemanticSearchRequest(query="variance", limit=2),
            FakeEmbeddings(),
            config(),
        )
    assert [hit.question.id for hit in result.items] == ["q-0", "q-1"]
