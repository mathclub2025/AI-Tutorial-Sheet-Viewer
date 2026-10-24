"""Environment configuration for the integration service; no database or storage."""

from enum import Enum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendMode(str, Enum):
    UNCONFIGURED = "unconfigured"
    DEMO = "demo"
    HTTP = "http"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    app_env: Literal["development", "testing", "production"] = "development"
    backend_mode: BackendMode = BackendMode.UNCONFIGURED
    app_name: str = "MathClub API"
    api_key: str | None = Field(None, repr=False)
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    cors_allow_credentials: bool = False
    person2_base_url: str | None = None
    ai_base_url: str | None = None
    internal_service_token: str | None = Field(None, repr=False)
    person2_service_token: str | None = Field(None, repr=False)
    ai_service_token: str | None = Field(None, repr=False)
    document_dispatch_token: str | None = Field(None, repr=False)
    ai_callback_token: str | None = Field(None, repr=False)
    upstream_timeout_seconds: float = Field(default=15, gt=0, le=60)
    request_timeout_seconds: float = Field(default=45, gt=0, le=180)
    health_timeout_seconds: float = Field(default=2, gt=0, le=10)
    upstream_read_retries: int = Field(default=1, ge=0, le=2)
    circuit_failure_threshold: int = Field(default=5, ge=1, le=100)
    circuit_reset_seconds: float = Field(default=30, gt=0, le=300)
    upstream_max_response_bytes: int = Field(default=4_194_304, ge=1024, le=16_777_216)
    max_request_bytes: int = Field(default=65_536, ge=1024, le=1_048_576)
    max_internal_request_bytes: int = Field(default=4_194_304, ge=1024, le=16_777_216)
    request_body_timeout_seconds: float = Field(default=15, gt=0, le=60)
    rate_limit_per_minute: int = Field(default=120, ge=0, le=10000)
    internal_rate_limit_per_minute: int = Field(default=300, ge=0, le=10000)
    capture_required: bool = False

    def token_for(self, purpose: str) -> str | None:
        return getattr(self, purpose) or self.internal_service_token

    @property
    def allowed_origins(self) -> list[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]

    @model_validator(mode="after")
    def check_security_and_integrations(self):
        for field in ("person2_base_url", "ai_base_url"):
            value = getattr(self, field)
            if value:
                url = urlsplit(value)
                if (
                    url.scheme not in {"http", "https"}
                    or not url.hostname
                    or url.username
                    or url.password
                    or url.query
                    or url.fragment
                    or url.path not in {"", "/"}
                ):
                    raise ValueError(
                        f"{field} must be an HTTP(S) origin without credentials or a path"
                    )
        for origin in self.allowed_origins:
            url = urlsplit(origin)
            if (
                url.scheme not in {"http", "https"}
                or not url.netloc
                or url.path
                or url.query
                or url.fragment
                or url.username
                or url.password
            ):
                raise ValueError("CORS_ORIGINS must contain explicit origins without paths")
        if self.backend_mode == BackendMode.HTTP and not (
            self.person2_base_url and self.ai_base_url
        ):
            raise ValueError("HTTP mode requires PERSON2_BASE_URL and AI_BASE_URL")
        if self.app_env == "production":
            if self.backend_mode != BackendMode.HTTP:
                raise ValueError("Production must use BACKEND_MODE=http")
            if not self.capture_required:
                raise ValueError("CAPTURE_REQUIRED must be true in production")
            secrets = [
                self.api_key,
                self.person2_service_token,
                self.ai_service_token,
                self.document_dispatch_token,
                self.ai_callback_token,
                self.internal_service_token,
            ]
            if any(
                not secret
                or len(secret) < 32
                or secret.lower().startswith(("change", "replace", "local-dev"))
                for secret in secrets
            ):
                raise ValueError(
                    "Production requires six separate secrets of at least 32 characters"
                )
            if len(set(secrets)) != len(secrets):
                raise ValueError("Production service credentials must be distinct")
        return self
