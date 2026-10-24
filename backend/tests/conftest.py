import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def demo_client():
    settings = Settings(
        _env_file=None, app_env="testing", backend_mode="demo", api_key="test-secret"
    )
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def headers():
    return {"X-API-Key": "test-secret", "X-Request-ID": "mathclub-test-1234"}
