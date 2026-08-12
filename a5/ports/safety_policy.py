from __future__ import annotations

from typing import Protocol, runtime_checkable

from a5.domain.models import Question, SafetyAssessment


@runtime_checkable
class SafetyPolicy(Protocol):
    def assess(self, question: Question) -> SafetyAssessment:
        """Assess whether A5 may answer under the configured A1 policy."""
        ...
