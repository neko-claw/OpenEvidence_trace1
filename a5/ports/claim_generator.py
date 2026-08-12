from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from a5.domain.models import AgentPlan, Claim, EvidenceRecord, Question


@runtime_checkable
class ClaimGenerator(Protocol):
    def generate(
        self,
        question: Question,
        evidence: Sequence[EvidenceRecord],
        plan: AgentPlan,
        run_id: str,
    ) -> list[Claim]:
        """Generate candidate claims using only supplied Evidence/Span IDs."""
        ...
