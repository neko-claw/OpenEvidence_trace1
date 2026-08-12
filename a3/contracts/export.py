from __future__ import annotations

import json
from pathlib import Path

from a3.domain.models import Chunk, Evidence, EvidenceSpan, IndexManifest, SearchHit

MODELS = {"Evidence": Evidence, "Chunk": Chunk, "EvidenceSpan": EvidenceSpan,
          "SearchHit": SearchHit, "IndexManifest": IndexManifest}


def export_schemas(output: str | Path) -> list[Path]:
    root = Path(output); root.mkdir(parents=True, exist_ok=True); paths = []
    for name, model in MODELS.items():
        path = root / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2,
            sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


if __name__ == "__main__":
    export_schemas(Path(__file__).resolve().parents[2] / "contracts/a3/v0.3/schemas")
