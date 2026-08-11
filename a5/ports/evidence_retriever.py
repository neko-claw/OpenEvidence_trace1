from __future__ import annotations

from typing import Protocol, runtime_checkable

from a5.domain.models import Question, RetrievalResult, SearchPlan


@runtime_checkable
class EvidenceRetriever(Protocol):
    def retrieve(self, question: Question, plan: SearchPlan) -> RetrievalResult:
        """Return evidence already normalized to the temporary A5 view."""
        ...
