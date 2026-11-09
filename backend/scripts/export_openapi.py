"""Regenerate docs/openapi.json after modifying routes/models."""

import json
from pathlib import Path

from app.config import Settings
from app.data_service.main import create_data_app
from app.data_service.settings import DataServiceSettings
from app.main import create_app

app = create_app(Settings(_env_file=None, app_env="testing", backend_mode="unconfigured"))
target = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
target.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print(f"Exported {target}")

data_app = create_data_app(DataServiceSettings(_env_file=None))
data_target = target.with_name("openapi-data-service.json")
data_target.write_text(json.dumps(data_app.openapi(), indent=2) + "\n", encoding="utf-8")
print(f"Exported {data_target}")
