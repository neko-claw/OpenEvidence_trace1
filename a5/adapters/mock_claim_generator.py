from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from a5.domain.models import AgentPlan, Claim, EvidenceRecord, Question


class MockClaimGenerator:
    """Deterministic offline generator driven only by explicit mock metadata."""

    def generate(
        self,
        question: Question,
        evidence: Sequence[EvidenceRecord],
        plan: AgentPlan,
    ) -> list[Claim]:
        del plan
        claims: list[Claim] = []
        seen: set[str] = set()
        for record in evidence:
            raw_claims = record.source_metadata.get("mock_claims", [])
            for raw_claim in raw_claims:
                claim = Claim.model_validate(raw_claim)
                if claim.claim_id not in seen:
                    claims.append(claim)
                    seen.add(claim.claim_id)

        illegal_id = question.metadata.get("inject_illegal_evidence_id")
        if illegal_id and claims:
            payload: dict[str, Any] = claims[0].model_dump()
            payload["evidence_ids"] = [str(illegal_id)]
            claims[0] = Claim.model_validate(payload)
        return claims
