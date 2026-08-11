from __future__ import annotations

import json
from pathlib import Path

from a5.domain.models import EvidenceRecord, Question, RetrievalResult, SearchPlan


class MockEvidenceRetriever:
    """Offline test adapter; never represents real medical retrieval."""

    def __init__(self, fixture_path: Path | None = None) -> None:
        default_path = Path(__file__).parents[1] / "fixtures" / "evidence.json"
        self._fixture_path = fixture_path or default_path
        self._records = self._load_records(self._fixture_path)

    @staticmethod
    def _load_records(path: Path) -> dict[str, EvidenceRecord]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = [EvidenceRecord.model_validate(item) for item in payload]
        if any(not record.mock for record in records):
            raise ValueError("MockEvidenceRetriever accepts only mock=true fixtures")
        if len(records) != len({record.id for record in records}):
            raise ValueError("mock evidence IDs must be unique")
        return {record.id: record for record in records}

    def retrieve(self, question: Question, plan: SearchPlan) -> RetrievalResult:
        requested_ids = question.metadata.get("fixture_evidence_ids")
        if requested_ids is None:
            selected = list(self._records.values())
        else:
            selected = [
                self._records[evidence_id]
                for evidence_id in requested_ids
                if evidence_id in self._records
            ]

        return RetrievalResult(
            evidence=selected,
            tool_name="mock_search",
            diagnostics={
                "adapter": type(self).__name__,
                "fixture": self._fixture_path.name,
                "requested_count": len(requested_ids) if requested_ids is not None else None,
                "query_count": len(plan.queries),
                "mock": True,
            },
        )
