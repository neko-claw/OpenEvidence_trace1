from __future__ import annotations

from a5.domain.enums import SafetyDecision
from a5.domain.models import Question, SafetyAssessment
from a5.runtime_config import load_runtime_config


class DefaultFailClosedSafetyPolicy:
    """Temporary Gate0 policy: without an A1 decision, refuse as UNKNOWN."""

    def __init__(self, version: str | None = None) -> None:
        gate_version = version or load_runtime_config().gates.gate0_version
        self.version = f"default_fail_closed@{gate_version}"

    def assess(self, question: Question) -> SafetyAssessment:
        del question
        return SafetyAssessment(
            decision=SafetyDecision.UNKNOWN,
            reason="safety_unknown: A1 safety/scope policy has not supplied ALLOW",
            policy_version=self.version,
        )


class FixtureSafetyPolicy:
    """Offline-only adapter requiring an explicit fixture safety decision."""

    def __init__(self, version: str | None = None) -> None:
        gate_version = version or load_runtime_config().gates.gate0_version
        self.version = f"mock_fixture_safety@{gate_version}"

    def assess(self, question: Question) -> SafetyAssessment:
        raw = question.metadata.get("mock_safety_decision", "UNKNOWN")
        try:
            decision = SafetyDecision(str(raw).upper())
        except ValueError:
            decision = SafetyDecision.UNKNOWN
        return SafetyAssessment(
            decision=decision,
            reason=f"mock Gate0 decision={decision.value}; not an A1 medical policy",
            policy_version=self.version,
        )


# Compatibility import for callers; semantics are now fail-closed.
DefaultSafetyPolicy = DefaultFailClosedSafetyPolicy
