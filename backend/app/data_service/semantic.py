"""Embedding providers, query chunking and exact pgvector semantic search."""

import math
import re
import threading
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.core.errors import ServiceError
from app.data_service.service import DataService
from app.domain.management import EmbeddingRequest, EmbeddingResponse
from app.domain.models import SearchEnvelope, SearchHit
from app.persistence.models import Answer, QuestionEmbedding, QuestionRecord

MAX_QUERY_CHUNKS = 8
CANDIDATES_PER_CHUNK = 10
SENTENCE_BOUNDARY = re.compile(r"(?<=[.?!])\s+|\n+")


def normalize(vector, dimensions):
    if len(vector) != dimensions or any(not math.isfinite(v) for v in vector):
        raise ServiceError("INVALID_EMBEDDING", "Embedding dimensions or values are invalid", 502)
    norm = math.sqrt(sum(v * v for v in vector))
    if not math.isfinite(norm) or norm <= 0:
        raise ServiceError("INVALID_EMBEDDING", "Embedding must be a finite nonzero vector", 502)
    return [float(v / norm) for v in vector]


class LocalEmbeddings:
    def __init__(self, settings, client=None):
        self.settings, self.client = settings, client

    def embed(self, texts):
        cfg = self.settings
        if not cfg.embedding_base_url or not cfg.embedding_service_token:
            raise ServiceError(
                "EMBEDDINGS_NOT_CONFIGURED", "Configure the local embedding service", 503
            )
        request = EmbeddingRequest(texts=texts, model=cfg.embedding_model, request_id=str(uuid4()))
        owned = self.client is None
        client = self.client or httpx.Client(timeout=30, trust_env=False, follow_redirects=False)
        try:
            with client.stream(
                "POST",
                cfg.embedding_base_url.rstrip("/") + "/internal/v1/embeddings",
                json=request.model_dump(),
                headers={
                    "X-Internal-Token": cfg.embedding_service_token.get_secret_value(),
                    "X-Request-ID": request.request_id,
                },
                timeout=30,
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise ServiceError(
                        "EMBEDDING_SERVICE_UNAVAILABLE",
                        "Embedding service rejected the request",
                        503,
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 4_194_304:
                        raise ServiceError(
                            "INVALID_EMBEDDING", "Embedding response is too large", 502
                        )
                try:
                    result = EmbeddingResponse.model_validate_json(body)
                except ValueError as exc:
                    raise ServiceError(
                        "INVALID_EMBEDDING", "Embedding response is invalid", 502
                    ) from exc
            if result.model != cfg.embedding_model or len(result.vectors) != len(texts):
                raise ServiceError(
                    "INVALID_EMBEDDING", "Embedding model or batch count does not match", 502
                )
            return [normalize(v, cfg.embedding_dimensions) for v in result.vectors]
        except httpx.RequestError as exc:
            raise ServiceError(
                "EMBEDDING_SERVICE_UNAVAILABLE", "Local embedding service is unreachable", 503
            ) from exc
        finally:
            if owned:
                client.close()


class FastEmbedEmbeddings:
    def __init__(self, settings):
        self.settings = settings
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise ServiceError(
                "EMBEDDING_PROVIDER_UNAVAILABLE", "Install the fastembed embedding extra", 503
            ) from exc
        try:
            return TextEmbedding(model_name=self.settings.embedding_model)
        except Exception as exc:
            raise ServiceError(
                "EMBEDDING_PROVIDER_UNAVAILABLE",
                "The configured fastembed embedding model could not be loaded",
                503,
            ) from exc

    def instance(self):
        with self._lock:
            if self._model is None:
                self._model = self._load()
            return self._model

    def embed(self, texts):
        if not texts:
            raise ServiceError(
                "INVALID_EMBEDDING", "Embedding requests require at least one text", 502
            )
        model = self.instance()
        try:
            vectors = list(model.embed(texts))
        except Exception as exc:
            raise ServiceError(
                "EMBEDDING_PROVIDER_UNAVAILABLE", "The fastembed model rejected the batch", 503
            ) from exc
        if len(vectors) != len(texts):
            raise ServiceError("INVALID_EMBEDDING", "Embedding batch count does not match", 502)
        return [normalize(vector, self.settings.embedding_dimensions) for vector in vectors]


def build_embeddings(settings):
    provider = (settings.embedding_provider or "http").lower()
    if provider == "http":
        return LocalEmbeddings(settings)
    if provider == "fastembed":
        return FastEmbedEmbeddings(settings)
    raise ServiceError("EMBEDDING_PROVIDER_UNKNOWN", "Configure a supported embedding provider", 503)


def chunk_query(query, max_chunks=MAX_QUERY_CHUNKS):
    parts = [part.strip() for part in SENTENCE_BOUNDARY.split(query) if part.strip()]
    return parts[:max_chunks]


def embedding_text(session, question):
    answer = session.scalar(
        select(Answer)
        .where(
            Answer.question_id == question.id,
            Answer.review_status == "approved",
        )
        .order_by(Answer.created_at, Answer.id)
        .limit(1)
    )
    return "\n".join(
        filter(
            None,
            [
                question.subject.name if question.subject else None,
                question.module.name if question.module else None,
                " ".join(sorted(a.topic.name for a in question.topics)),
                question.question_text,
                answer.answer_text if answer else None,
            ],
        )
    )


def semantic_search(session, payload, embeddings, config):
    chunks = chunk_query(payload.query)
    if not chunks:
        return SearchEnvelope(items=[])
    vectors = embeddings.embed(chunks)
    base = (
        DataService()
        ._question_query(payload.filters)
        .join(
            QuestionEmbedding,
            QuestionEmbedding.question_id == QuestionRecord.id,
        )
        .where(
            QuestionEmbedding.model_name == config.embedding_model,
            QuestionEmbedding.content_revision == QuestionRecord.revision,
        )
    )
    best = {}
    if session.bind.dialect.name == "postgresql":
        for vector in vectors:
            distance = QuestionEmbedding.embedding.cosine_distance(
                normalize(vector, config.embedding_dimensions)
            )
            rows = session.execute(
                base.add_columns(distance.label("distance"))
                .where(distance <= 1 - payload.min_score)
                .order_by(distance, QuestionRecord.external_id)
                .limit(CANDIDATES_PER_CHUNK)
            ).all()
            for question, value in rows:
                score = max(0.0, min(1.0, 1 - value))
                current = best.get(question.id)
                if current is None or score > current[0]:
                    best[question.id] = (score, question)
    else:
        for vector in vectors:
            query_vector = normalize(vector, config.embedding_dimensions)
            for question in session.scalars(base):
                stored = session.get(QuestionEmbedding, question.id)
                stored_vector = normalize(stored.embedding, config.embedding_dimensions)
                score = max(
                    0.0,
                    min(1.0, sum(a * b for a, b in zip(query_vector, stored_vector, strict=True))),
                )
                if score < payload.min_score:
                    continue
                current = best.get(question.id)
                if current is None or score > current[0]:
                    best[question.id] = (score, question)
    ranked = sorted(best.values(), key=lambda pair: (-pair[0], pair[1].external_id))
    return SearchEnvelope(
        items=[
            SearchHit(question=DataService._to_question(session, question), relevance_score=score)
            for score, question in ranked[: payload.limit]
        ]
    )
