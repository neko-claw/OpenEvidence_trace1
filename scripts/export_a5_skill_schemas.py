from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from a5.domain.models import (
    CitationAuditInput,
    CitationAuditOutput,
    EvidenceResearchInput,
    EvidenceResearchOutput,
)


OUTPUTS = {
    ROOT / "a5/skills/evidence_research/input.schema.json": EvidenceResearchInput,
    ROOT / "a5/skills/evidence_research/output.schema.json": EvidenceResearchOutput,
    ROOT / "a5/skills/citation_audit/input.schema.json": CitationAuditInput,
    ROOT / "a5/skills/citation_audit/output.schema.json": CitationAuditOutput,
}


def main() -> None:
    for path, model in OUTPUTS.items():
        path.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
