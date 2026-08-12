from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from a5.domain.models import Claim, EvidenceRecord, TextualSupportAssessment


@runtime_checkable
class TextualSupportEvaluator(Protocol):
    """Extension point for exact-match, LLM, NLI, or medical evaluators."""

    def evaluate(
        self,
        claim: Claim,
        evidence: Sequence[EvidenceRecord],
    ) -> TextualSupportAssessment:
        ...
