from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.persistence.settings import PersistenceSettings


class DataServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    person2_inbound_token: SecretStr | None = Field(None, repr=False)
    app_env: Literal["development", "testing", "production"] = "development"
    ai_data_token: SecretStr | None = Field(None, repr=False)
    person1_base_url: str = "http://127.0.0.1:8000"
    document_dispatch_token: SecretStr | None = Field(None, repr=False)
    embedding_provider: str = "http"
    embedding_base_url: str | None = None
    embedding_service_token: SecretStr | None = Field(None, repr=False)
    embedding_model: str = "mathclub-local-v1"
    embedding_dimensions: int = Field(default=384, ge=1, le=4096)
    session_hours: int = Field(default=8, ge=1, le=24)
    worker_max_attempts: int = Field(default=5, ge=1, le=20)
    worker_lease_seconds: int = Field(default=120, ge=60, le=600)
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    # Same intake limits as the gateway. Upload bytes go directly to object storage.
    rate_limit_per_minute: int = Field(default=120, ge=0, le=10000)
    internal_rate_limit_per_minute: int = Field(default=300, ge=0, le=10000)
    max_request_bytes: int = Field(default=65536, ge=1024, le=1048576)
    max_internal_request_bytes: int = Field(default=4194304, ge=1024, le=16777216)
    request_body_timeout_seconds: float = Field(default=15, gt=0, le=60)
    request_timeout_seconds: float = Field(default=90, gt=0, le=180)

    @property
    def allowed_origins(self):
        return [v.strip() for v in self.cors_origins.split(",") if v.strip()]

    @model_validator(mode="after")
    def valid_origins(self):
        for value in [self.person1_base_url, self.embedding_base_url, *self.allowed_origins]:
            if value is None:
                continue
            url = urlsplit(value)
            if (url.scheme not in {"http", "https"} or not url.hostname or url.username
                    or url.password or url.query or url.fragment or url.path not in {"", "/"}):
                raise ValueError("Service URLs and CORS entries must be explicit HTTP(S) origins")
        if self.app_env == "production":
            tokens = [self.person2_inbound_token, self.ai_data_token, self.document_dispatch_token]
            if self.embedding_base_url:
                tokens.append(self.embedding_service_token)
            values = [v.get_secret_value() if v else "" for v in tokens]
            if any(len(v) < 32 or v.lower().startswith(("replace", "change", "local-dev")) for v in values):
                raise ValueError("Production data-service credentials must be non-placeholder secrets of at least 32 characters")
            if len(values) != len(set(values)):
                raise ValueError("Data-service credentials must be distinct by purpose")
        return self

    def database_url(self) -> str:
        configured = PersistenceSettings().database_url
        if configured is None:
            raise ValueError("DATABASE_URL must be configured for the data service")
        return configured.get_secret_value()
