"""Backend-owned management contracts; independent of any UI implementation."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.models import Identifier, SearchRequest, SourceType, StrictModel

Role = Literal["admin", "reviewer", "uploader"]
ReviewStatus = Literal["draft", "pending_review", "approved", "rejected", "archived"]


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("password", mode="before")
    @classmethod
    def preserve_password(cls, value):
        return value

    model_config = {"extra": "forbid", "str_strip_whitespace": False}


class UserView(StrictModel):
    id: UUID
    name: str
    email: str
    role: Role
    is_active: bool


class UserCreate(LoginRequest):
    name: str = Field(min_length=1, max_length=200)
    role: Role = "uploader"
    password: str = Field(min_length=12, max_length=1024)


class UserUpdate(StrictModel):
    role: Role | None = None
    is_active: bool | None = None


class SessionView(StrictModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserView


class FileRequest(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=127)
    size_bytes: int = Field(gt=0, le=15_728_640, strict=True)
    sha256: str | None = Field(None, pattern=r"^[a-fA-F0-9]{64}$")
    client_upload_key: str = Field(min_length=8, max_length=128, pattern=r"^[\w.:-]+$")

    @field_validator("filename")
    @classmethod
    def basename_only(cls, value):
        if any(c in value for c in ("/", "\\", "\x00", "\r", "\n")):
            raise ValueError("Use a filename, not a path")
        return value


class DocumentUpload(FileRequest):
    title: str = Field(min_length=1, max_length=500)
    document_type: Literal["question_paper", "answer_sheet", "tutorial_sheet", "other"]
    source_type: SourceType
    subject: str = Field(min_length=1, max_length=100)
    module: str | None = Field(None, min_length=1, max_length=100)
    year: int | None = Field(None, ge=1990, le=2100, strict=True)
    process: bool = True


class AssetUpload(FileRequest):
    document_id: Identifier
    document_version: str = Field(min_length=1, max_length=100)
    kind: Literal["question_image", "solution_image"]


class UploadView(StrictModel):
    id: UUID
    method: Literal["PUT"] = "PUT"
    upload_url: str | None
    required_headers: dict[str, str]
    expires_at: datetime
    confirmed: bool
    document_id: str | None = None
    asset_id: UUID | None = None


class DocumentView(StrictModel):
    id: str
    title: str
    document_type: str
    source_type: SourceType | None
    document_version: str
    filename: str
    size_bytes: int
    subject: str | None
    module: str | None
    year: int | None
    visibility: str
    processing_status: str
    indexing_status: str
    created_at: datetime
    question_count: int = 0
    approved_count: int = 0
    flagged_count: int = 0
    pending_count: int = 0


class DocumentPage(StrictModel):
    items: list[DocumentView]
    total: int
    offset: int
    limit: int


class PublicationRequest(StrictModel):
    visibility: Literal["private", "public"]


class QuestionEdit(StrictModel):
    expected_revision: int = Field(ge=1, strict=True)
    text: str | None = Field(None, min_length=1, max_length=15000)
    subject: str | None = Field(None, min_length=1, max_length=100)
    module: str | None = Field(None, min_length=1, max_length=100)
    topic: str | None = Field(None, min_length=1, max_length=100)
    topics: list[str] | None = Field(None, max_length=30)
    difficulty: Literal["easy", "medium", "hard"] | None = None

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, value):
        if value is None:
            return value
        result = []
        for item in value:
            item = item.strip()
            if not 1 <= len(item) <= 100:
                raise ValueError("Topics must contain 1 to 100 characters")
            if item.casefold() not in {t.casefold() for t in result}:
                result.append(item)
        return result
    official_solution: str | None = Field(None, min_length=1, max_length=30000)
    solution_document_id: Identifier | None = None
    question_asset_id: UUID | None = None
    solution_asset_id: UUID | None = None

    @model_validator(mode="after")
    def required_values_not_null(self):
        if "topic" in self.model_fields_set and "topics" in self.model_fields_set:
            raise ValueError("Send topic or topics, not both")
        for key in ("text", "subject"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be cleared")
        return self


class ReviewRequest(StrictModel):
    expected_revision: int = Field(ge=1, strict=True)
    status: Literal["approved", "rejected", "pending_review", "archived"]
    note: str | None = Field(None, max_length=2000)
    approve_solution: bool = False
    flagged: bool = False

    @model_validator(mode="after")
    def flag_requires_note(self):
        if self.flagged and (self.status != "pending_review" or not self.note):
            raise ValueError("Flags require pending_review status and a note")
        return self


class ReviewQuestion(StrictModel):
    id: str
    document_id: str
    revision: int
    status: str
    text: str
    subject: str | None
    module: str | None
    topic: str | None
    page_number: int | None
    question_number: str | None
    official_solution: str | None
    solution_status: str | None
    solution_document_id: str | None
    question_asset_id: UUID | None
    solution_asset_id: UUID | None
    topics: list[str] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"] | None = None
    flag_note: str | None = None
    source_type: SourceType | None = None
    year: int | None = None
    document_version: str = "v1"


class QuestionPage(StrictModel):
    items: list[ReviewQuestion]
    total: int
    offset: int
    limit: int


class TaskView(StrictModel):
    id: UUID
    kind: str
    status: str
    attempts: int
    next_attempt_at: datetime
    last_error: str | None
    payload: dict
    created_at: datetime


class TaskPage(StrictModel):
    items: list[TaskView]
    total: int
    offset: int
    limit: int


class AssetLinks(StrictModel):
    question_id: str
    question_image_url: str | None = None
    solution_image_url: str | None = None
    solution_document_id: str | None = None
    expires_in_seconds: int


class DownloadView(StrictModel):
    document: DocumentView
    download_url: str
    expires_in_seconds: int


class SemanticSearchRequest(SearchRequest):
    min_score: float = Field(default=0.7, ge=0, le=1, allow_inf_nan=False)


class EmbeddingRequest(StrictModel):
    texts: list[str] = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=255)
    request_id: str


class EmbeddingResponse(StrictModel):
    model: str
    vectors: list[list[float]] = Field(min_length=1, max_length=32)


class DocumentClassification(StrictModel):
    expected_source_type: SourceType
    source_type: Literal["tutorial", "pyq"]
