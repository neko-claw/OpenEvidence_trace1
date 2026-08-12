from __future__ import annotations

import json
from pathlib import Path

from a2.models.evidence import A2Evidence
from a2.models.tool_response import ToolResponse


SCHEMA_MODELS = {
    "Evidence.schema.json": A2Evidence,
    "ToolResponse.schema.json": ToolResponse,
}


def rendered_schemas() -> dict[str, str]:
    return {
        filename: json.dumps(
            model.model_json_schema(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
        for filename, model in SCHEMA_MODELS.items()
    }


def export_schemas(root: str | Path) -> list[Path]:
    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for filename, content in rendered_schemas().items():
        path = target / filename
        path.write_text(content, encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


if __name__ == "__main__":
    export_schemas(Path(__file__).resolve().parents[1] / "contracts" / "a2" / "v1" / "schemas")
