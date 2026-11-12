"""Pydantic v2 schemas for API requests, responses, and errors."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.extraction.schemas.extraction import PaperExtractionResult


class HealthResponse(BaseModel):
    """Schema for GET /health endpoint response."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="healthy", description="Service health status")
    version: str = Field(..., description="API service version")
    gemini_configured: bool = Field(
        ...,
        description="Whether a valid GEMINI_API_KEY is detected in environment configuration",
    )


class ImageMetadata(BaseModel):
    """Schema for preprocessed image metadata."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    content_type: str
    original_size_bytes: int
    dimensions: Dict[str, int] = Field(
        description="Dimensions of preprocessed image {'width': int, 'height': int}"
    )
    page_count: Optional[int] = Field(
        default=None,
        description="Total page count if document is a multi-page PDF.",
    )


class PaperExtractResponse(BaseModel):
    """Schema for successful extraction response on POST /api/v1/papers/extract."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(default=True, description="Whether the extraction completed")
    data: PaperExtractionResult = Field(
        ...,
        description="Validated mathematical extraction result according to schema",
    )
    image_metadata: ImageMetadata = Field(
        ...,
        description="Metadata of the uploaded and processed image",
    )
    processing_time_ms: float = Field(
        ...,
        ge=0.0,
        description="Total server-side processing duration in milliseconds",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Informational warnings regarding image quality or model uncertainty",
    )


class ErrorResponse(BaseModel):
    """Standardized API error response schema."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(default=False)
    error: str = Field(..., description="Error classification or message")
    details: Optional[Any] = Field(
        default=None,
        description="Detailed contextual information, validation errors, or hints",
    )
