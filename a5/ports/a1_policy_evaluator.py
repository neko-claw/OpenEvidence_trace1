from __future__ import annotations

from typing import Protocol, runtime_checkable

@runtime_checkable
class A1PolicyEvaluator(Protocol):
    """Callable A1 boundary; A5 never reimplements A1 medical policy rules."""

    def assess(self, policy_input: object) -> object:
        """Return A1 SafetyPolicyOutput for normalized Gate0 signals."""
        ...
