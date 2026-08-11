from __future__ import annotations

from typing import Protocol, runtime_checkable

from a5.domain.models import Question, RetrievalRequest, RetrievalResult, SearchPlan


@runtime_checkable
class EvidenceRetriever(Protocol):
    def retrieve(
        self,
        question: Question,
        plan: SearchPlan,
        request: RetrievalRequest,
    ) -> RetrievalResult:
        """Return one bounded tool call normalized to the temporary A5 view."""
        ...
