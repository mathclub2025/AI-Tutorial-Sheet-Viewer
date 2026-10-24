from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.persistence.settings import PersistenceSettings


class DataServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    person2_inbound_token: SecretStr | None = Field(None, repr=False)

    def database_url(self) -> str:
        configured = PersistenceSettings().database_url
        if configured is None:
            raise ValueError("DATABASE_URL must be configured for the data service")
        return configured.get_secret_value()
