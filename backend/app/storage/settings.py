from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.storage.b2 import B2Settings


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    b2_endpoint_url: str | None = None
    b2_bucket_name: str | None = None
    b2_access_key_id: SecretStr | None = Field(None, repr=False)
    b2_application_key: SecretStr | None = Field(None, repr=False)
    b2_region: str = "us-west-004"
    cloudflare_delivery_base_url: str | None = None
    b2_signed_url_expiry_seconds: int = Field(default=900, ge=1, le=604800)
    max_upload_bytes: int = Field(default=52_428_800, ge=1)

    @model_validator(mode="after")
    def validate_b2_configuration(self):
        configured = (
            self.b2_endpoint_url,
            self.b2_bucket_name,
            self.b2_access_key_id,
            self.b2_application_key,
        )
        if any(configured) and not all(configured):
            raise ValueError(
                "B2_ENDPOINT_URL, B2_BUCKET_NAME, B2_ACCESS_KEY_ID, and "
                "B2_APPLICATION_KEY must be configured together"
            )
        if self.b2_endpoint_url:
            endpoint = urlsplit(self.b2_endpoint_url)
            if (
                endpoint.scheme != "https"
                or not endpoint.hostname
                or endpoint.username
                or endpoint.password
                or endpoint.path
                or endpoint.query
                or endpoint.fragment
            ):
                raise ValueError("B2_ENDPOINT_URL must be an HTTPS origin without credentials")
        if self.cloudflare_delivery_base_url:
            delivery = urlsplit(self.cloudflare_delivery_base_url)
            if (
                delivery.scheme not in {"http", "https"}
                or not delivery.hostname
                or delivery.username
                or delivery.password
                or delivery.query
                or delivery.fragment
            ):
                raise ValueError(
                    "CLOUDFLARE_DELIVERY_BASE_URL must be HTTP(S) without credentials or query"
                )
        return self

    def to_b2_settings(self) -> B2Settings:
        if not self.b2_endpoint_url:
            raise ValueError("B2 storage is not configured")

        return B2Settings(
            endpoint_url=self.b2_endpoint_url,
            bucket_name=self.b2_bucket_name or "",
            access_key_id=self.b2_access_key_id.get_secret_value(),
            secret_access_key=self.b2_application_key.get_secret_value(),
            region=self.b2_region,
            delivery_base_url=self.cloudflare_delivery_base_url,
            signed_url_expiry_seconds=self.b2_signed_url_expiry_seconds,
            max_upload_bytes=self.max_upload_bytes,
        )
