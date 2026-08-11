from __future__ import annotations

import json
from pathlib import Path

from a5.domain.models import (
    EvidenceRecord,
    Question,
    RetrievalRequest,
    RetrievalResult,
    SearchPlan,
)


class MockEvidenceRetriever:
    """Offline test adapter; each invocation is one observable tool call."""

    def __init__(self, fixture_path: Path | None = None) -> None:
        default_path = Path(__file__).parents[1] / "fixtures" / "evidence.json"
        self._fixture_path = fixture_path or default_path
        self._records = self._load_records(self._fixture_path)
        self.call_count = 0

    @staticmethod
    def _load_records(path: Path) -> dict[str, EvidenceRecord]:
        records = [
            EvidenceRecord.model_validate(item)
            for item in json.loads(path.read_text(encoding="utf-8"))
        ]
        if any(not record.mock for record in records):
            raise ValueError("MockEvidenceRetriever accepts only mock=true fixtures")
        if len(records) != len({record.id for record in records}):
            raise ValueError("mock evidence IDs must be unique")
        return {record.id: record for record in records}

    def retrieve(
        self,
        question: Question,
        plan: SearchPlan,
        request: RetrievalRequest,
    ) -> RetrievalResult:
        self.call_count += 1
        batches = question.metadata.get("fixture_batches")
        if batches is not None:
            index = request.tool_call_index - 1
            requested_ids = batches[index] if index < len(batches) else []
        else:
            requested_ids = question.metadata.get("fixture_evidence_ids")
            if requested_ids is None:
                requested_ids = list(self._records)
            routed = [
                evidence_id
                for evidence_id in requested_ids
                if evidence_id in self._records
                and self._records[evidence_id].source_metadata.get("mock_route")
                == request.source_type
            ]
            if routed:
                requested_ids = routed
            elif request.tool_call_index > 1:
                requested_ids = []
        selected = [self._records[item] for item in requested_ids if item in self._records]
        return RetrievalResult(
            evidence=selected,
            tool_name="mock_search",
            diagnostics={
                "adapter": type(self).__name__,
                "fixture": self._fixture_path.name,
                "requested_source": request.source_type,
                "tool_call_index": request.tool_call_index,
                "query_count": len(plan.queries),
                "mock": True,
            },
        )
