from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from a5.domain.models import EvidenceIntegrityResult, EvidenceRecord


@runtime_checkable
class EvidenceIntegrityEvaluator(Protocol):
    """Gate1 source/provenance boundary; real source checks remain upstream."""

    def evaluate(self, evidence: Sequence[EvidenceRecord]) -> EvidenceIntegrityResult:
        ...
