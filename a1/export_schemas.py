from __future__ import annotations

import json
from pathlib import Path

from a1.models import (
    RetrievalTerminationInput,
    RetrievalTerminationOutput,
    SafetyPolicyInput,
    SafetyPolicyOutput,
)


SCHEMA_MODELS = {
    "safety_policy_input.schema.json": SafetyPolicyInput,
    "safety_policy_output.schema.json": SafetyPolicyOutput,
    "retrieval_termination_input.schema.json": RetrievalTerminationInput,
    "retrieval_termination_output.schema.json": RetrievalTerminationOutput,
}


def rendered_schemas() -> dict[str, str]:
    return {
        filename: json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
        for filename, model in SCHEMA_MODELS.items()
    }


def export_schemas(root: str | Path) -> None:
    target = Path(root) / "schemas" / "a1"
    target.mkdir(parents=True, exist_ok=True)
    for filename, content in rendered_schemas().items():
        (target / filename).write_text(content, encoding="utf-8")


if __name__ == "__main__":
    export_schemas(Path(__file__).resolve().parents[1])
