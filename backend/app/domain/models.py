"""Shared API contracts. These are proposals to freeze jointly with the other teams."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    ),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceType(str, Enum):
    TUTORIAL = "tutorial"
    PYQ = "pyq"
    PRACTICE = "practice"


class SearchFilters(StrictModel):
    subject: str | None = Field(None, min_length=1, max_length=100)
    module: str | None = Field(None, min_length=1, max_length=100)
    topic: str | None = Field(None, min_length=1, max_length=100)
    year: int | None = Field(None, ge=1990, le=2100, strict=True)
    source_type: SourceType | None = None


class SourceReference(StrictModel):
    source_type: SourceType
    document_id: Identifier | None = None
    document_title: str | None = Field(None, max_length=500)
    page_number: int | None = Field(None, ge=1)
    question_number: str | None = Field(None, max_length=100)
    year: int | None = Field(None, ge=1990, le=2100)


class Question(StrictModel):
    id: Identifier
    text: str = Field(min_length=1, max_length=15000)
    subject: str = Field(min_length=1, max_length=100)
    module: str | None = Field(None, max_length=100)
    topic: str | None = Field(None, max_length=100)
    source: SourceReference
    official_solution: str | None = Field(None, max_length=30000)
    # File/content delivery remains owned by Person 2. We never fetch or store the asset.
    image_url: str | None = Field(None, max_length=2048)

    @field_validator("image_url")
    @classmethod
    def safe_image_url(cls, value):
        if value is not None:
            from urllib.parse import urlsplit

            url = urlsplit(value)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
            ):
                raise ValueError("image_url must be an HTTP or HTTPS URL without credentials")
        return value


class SearchHit(StrictModel):
    question: Question
    relevance_score: float | None = Field(None, ge=0, le=1)


class SearchRequest(StrictModel):
    query: str = Field(min_length=3, max_length=2000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    limit: int = Field(default=5, ge=1, le=20, strict=True)


class SearchResponse(StrictModel):
    items: list[SearchHit]
    total: int = Field(ge=0)
    request_id: str
    captured: bool = False


class AskRequest(StrictModel):
    query: str | None = Field(None, min_length=3, max_length=2000)
    question_id: Identifier | None = None
    filters: SearchFilters = Field(default_factory=SearchFilters)
    limit: int = Field(default=5, ge=1, le=10, strict=True)
    explanation_level: Literal["beginner", "standard", "advanced"] = "standard"

    @model_validator(mode="after")
    def must_provide_query_or_question_id(self):
        if not self.query and not self.question_id:
            raise ValueError("Provide query or question_id")
        if self.question_id and any(v is not None for v in self.filters.model_dump().values()):
            raise ValueError("Filters cannot be combined with question_id")
        return self


class Citation(StrictModel):
    question_id: str
    source: SourceReference


class AskResponse(StrictModel):
    status: Literal["answered", "no_matches"]
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    matched_questions: list[SearchHit] = Field(default_factory=list)
    request_id: str
    captured: bool = False


class ExplainRequest(StrictModel):
    instruction: str | None = Field(None, min_length=1, max_length=1000)
    explanation_level: Literal["beginner", "standard", "advanced"] = "standard"


class ExplainResponse(StrictModel):
    answer: str
    citations: list[Citation]
    request_id: str
    captured: bool = False


class SimilarResponse(StrictModel):
    items: list[SearchHit]
    request_id: str


class AgentAnswer(StrictModel):
    answer: str = Field(min_length=1, max_length=30000)
    used_question_ids: list[Identifier] = Field(min_length=1, max_length=10)


class AgentAnswerRequest(StrictModel):
    query: str
    explanation_level: Literal["beginner", "standard", "advanced"]
    context: list[Question] = Field(min_length=1, max_length=10)
    request_id: str


class AgentExplainRequest(StrictModel):
    question: Question
    instruction: str | None = None
    explanation_level: Literal["beginner", "standard", "advanced"]
    request_id: str


class QueryEvent(StrictModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: Literal["search", "ask", "explain"]
    request_id: str
    query: str | None = None
    question_id: str | None = None
    filters: SearchFilters | None = None
    result_count: int | None = None


class ErrorBody(StrictModel):
    error: str
    message: str
    request_id: str
    details: list[dict] = Field(default_factory=list)


class DocumentDispatchRequest(StrictModel):
    """Person 2 sends an existing document ID; Person 1 never handles file bytes."""

    document_id: Identifier
    document_version: str = Field(min_length=1, max_length=100)
    source_type: SourceType
    # Retry-safe stable key supplied by the upstream uploader/ingestion service.
    client_job_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    )


class AgentDocumentJobRequest(DocumentDispatchRequest):
    request_id: str


class AgentDocumentJobAck(StrictModel):
    status: Literal["queued"]
    job_id: Identifier


class DocumentDispatchResponse(AgentDocumentJobAck):
    document_id: str
    request_id: str


class SearchEnvelope(StrictModel):
    items: list[SearchHit] = Field(max_length=100)


class FilterCatalog(StrictModel):
    """Valid subject/module/topic combinations supplied by the data service."""

    combinations: list[SearchFilters] = Field(max_length=5000)


class CatalogResponse(FilterCatalog):
    request_id: str


class JobFailure(StrictModel):
    code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Z0-9_]+$")
    message: str = Field(min_length=1, max_length=1000)


class DocumentJobStatus(DocumentDispatchRequest):
    job_id: Identifier
    status: Literal["queued", "processing", "completed", "failed"]
    progress: int = Field(ge=0, le=100, strict=True)
    extracted_count: int | None = Field(None, ge=0, le=100, strict=True)
    error: JobFailure | None = None

    @model_validator(mode="after")
    def consistent_status(self):
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("Only failed jobs must include error")
        if self.status == "completed" and (self.progress != 100 or self.extracted_count is None):
            raise ValueError("Completed jobs require progress 100 and extracted_count")
        if self.status == "queued" and self.progress != 0:
            raise ValueError("Queued jobs require progress 0")
        return self


class DocumentJobStatusResponse(DocumentJobStatus):
    request_id: str


class ExtractedQuestion(StrictModel):
    """AI-local ID; Person 2 assigns canonical question IDs during ingestion."""

    extraction_id: Identifier
    text: str = Field(min_length=1, max_length=15000)
    subject: str = Field(min_length=1, max_length=100)
    module: str | None = Field(None, max_length=100)
    topic: str | None = Field(None, max_length=100)
    source: SourceReference
    official_solution: str | None = Field(None, max_length=30000)
    confidence: float | None = Field(None, ge=0, le=1, allow_inf_nan=False)
    needs_review: bool = True


class DocumentResult(DocumentDispatchRequest):
    event_id: Identifier
    status: Literal["completed", "failed"]
    questions: list[ExtractedQuestion] = Field(default_factory=list, max_length=100)
    error: JobFailure | None = None

    @model_validator(mode="after")
    def consistent_result(self):
        if self.status == "failed":
            if self.error is None or self.questions:
                raise ValueError("Failed results require error and no questions")
        elif self.error is not None or not self.questions:
            raise ValueError("Completed results require questions and no error")
        ids = [q.extraction_id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("extraction_id values must be unique")
        if any(
            q.source.document_id != self.document_id
            or q.source.source_type != self.source_type
            or q.source.page_number is None
            for q in self.questions
        ):
            raise ValueError("Each source must match the document and type and include page_number")
        return self


class DocumentResultEvent(DocumentResult):
    job_id: Identifier
    request_id: str


class DocumentResultAck(StrictModel):
    accepted: Literal[True]
    event_id: Identifier
    job_id: Identifier
    document_id: Identifier
    document_version: str = Field(min_length=1, max_length=100)
    indexing_status: Literal["pending", "queued", "indexed", "not_applicable"]

    @field_validator("accepted", mode="before")
    @classmethod
    def literal_acknowledgement(cls, value):
        if value is not True:
            raise ValueError("accepted must be the JSON boolean true")
        return value


class DocumentResultResponse(DocumentResultAck):
    request_id: str
