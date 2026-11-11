"""Application settings and environment variable configuration."""

from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for the Maths Paper Parser API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Maths Paper Parser"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Gemini API Settings
    GEMINI_API_KEY: str = Field(
        default="",
        description="Google Gemini API Key for vision-based math extraction",
    )
    GEMINI_MODEL: str = Field(
        default="gemini-3.1-flash-lite",
        description="Gemini model identifier for vision-based document processing",
    )
    GEMINI_FALLBACK_MODEL: str = Field(
        default="gemini-3.5-flash",
        description="Optional verified single fallback Gemini model if primary is unavailable",
    )
    GEMINI_RECONCILIATION_MODEL: str = Field(
        default="gemini-3.5-flash",
        description="Configurable Gemini model identifier for Stage 2 cross-page hierarchy reconciliation",
    )
    GEMINI_RECONCILIATION_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        description="Timeout in seconds for Stage 2 cross-page reconciliation LLM calls",
    )
    GEMINI_RECONCILIATION_CHUNK_PAGES: int = Field(
        default=10,
        description="Maximum page chunk size for sliding-window reconciliation of large multi-page documents",
    )
    GEMINI_MAX_RETRIES: int = Field(
        default=2,
        description="Maximum retry attempts per model for transient errors",
    )
    GEMINI_BASE_RETRY_DELAY_SECONDS: float = Field(
        default=1.0,
        description="Base backoff delay in seconds",
    )
    GEMINI_MAX_RETRY_DELAY_SECONDS: float = Field(
        default=8.0,
        description="Maximum backoff delay between retries in seconds",
    )
    GEMINI_MAX_TOTAL_RETRY_DURATION_SECONDS: float = Field(
        default=25.0,
        description="Maximum total retry duration in seconds across all attempts",
    )

    # Upload limits & formats (Images + PDF)
    MAX_IMAGE_SIZE_MB: int = 15
    MAX_PDF_SIZE_MB: int = 25
    MAX_PDF_PAGES: int = 20
    PDF_RENDER_DPI: int = 200
    MAX_PAGE_DIMENSION_PX: int = 10000

    ALLOWED_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "webp", "pdf"]
    ALLOWED_MIME_TYPES: List[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    ]

    # CORS Settings
    CORS_ORIGINS: List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]



settings = Settings()
