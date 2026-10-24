"""Interfaces owned by Person 1, implemented by other teams or HTTP adapters."""

from typing import Protocol

from app.domain.models import (
    AgentAnswer,
    AgentAnswerRequest,
    AgentDocumentJobAck,
    AgentDocumentJobRequest,
    AgentExplainRequest,
    DocumentJobStatus,
    DocumentResultAck,
    DocumentResultEvent,
    FilterCatalog,
    QueryEvent,
    Question,
    SearchHit,
    SearchRequest,
)


class QuestionProvider(Protocol):
    async def catalog(self, trace_id: str) -> FilterCatalog: ...
    async def search(self, request: SearchRequest, trace_id: str) -> list[SearchHit]: ...
    async def get(self, question_id: str, trace_id: str) -> Question | None: ...
    async def similar(self, question_id: str, limit: int, trace_id: str) -> list[SearchHit]: ...


class AIProvider(Protocol):
    async def answer(self, request: AgentAnswerRequest) -> AgentAnswer: ...
    async def explain(self, request: AgentExplainRequest) -> AgentAnswer: ...


class QueryCapture(Protocol):
    async def record(self, event: QueryEvent) -> bool: ...


class DocumentJobProvider(Protocol):
    async def submit(self, request: "AgentDocumentJobRequest") -> "AgentDocumentJobAck": ...
    async def get(self, job_id: str, trace_id: str) -> DocumentJobStatus | None: ...


class DocumentResultSink(Protocol):
    async def accept(self, event: DocumentResultEvent) -> DocumentResultAck: ...


class DependencyHealth(Protocol):
    async def check(self, trace_id: str) -> dict[str, bool]: ...
