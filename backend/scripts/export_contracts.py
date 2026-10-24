"""Export the peer-service payload schemas not exposed by the public FastAPI routes."""

import json
from pathlib import Path

from app.domain import models

root = Path(__file__).resolve().parents[1] / "docs" / "contracts"
root.mkdir(parents=True, exist_ok=True)
for name in (
    "SearchRequest",
    "SearchEnvelope",
    "Question",
    "FilterCatalog",
    "QueryEvent",
    "AgentAnswerRequest",
    "AgentExplainRequest",
    "AgentAnswer",
    "AgentDocumentJobRequest",
    "AgentDocumentJobAck",
    "DocumentJobStatus",
    "DocumentResult",
    "DocumentResultEvent",
    "DocumentResultAck",
):
    schema = getattr(models, name).model_json_schema()
    (root / f"{name}.schema.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
print(f"Exported 14 peer payload schemas to {root}")
