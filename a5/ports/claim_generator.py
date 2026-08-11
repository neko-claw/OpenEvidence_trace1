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
    ) -> list[Claim]:
        """Generate atomic claims citing only IDs from the supplied evidence."""
        ...
