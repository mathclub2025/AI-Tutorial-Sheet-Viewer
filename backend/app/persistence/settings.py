from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PersistenceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: SecretStr | None = Field(None, repr=False)

    @model_validator(mode="after")
    def validate_database_url(self):
        if self.database_url:
            url = self.database_url.get_secret_value()
            if not url.startswith("postgresql+psycopg://"):
                raise ValueError("DATABASE_URL must use the postgresql+psycopg:// driver")
        return self
