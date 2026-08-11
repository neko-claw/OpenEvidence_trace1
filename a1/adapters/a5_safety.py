from __future__ import annotations

from pydantic import ValidationError

from a1.models import SafetyDecision as A1SafetyDecision
from a1.models import SafetyPolicyInput
from a1.policy import ReferenceSafetyPolicy
from a5.domain.enums import SafetyDecision as A5SafetyDecision
from a5.domain.models import Question, SafetyAssessment


class A1SafetyPolicyAdapter:
    """Adapt normalized A1 Gate0 signals to the A5 ``SafetyPolicy`` port.

    No free-text safety classification happens here. The normalized payload is
    expected at ``question.metadata['a1_safety_signals']``. Missing or invalid
    payloads are mapped to UNKNOWN, preserving A5's fail-closed behavior.
    """

    def __init__(self, policy: ReferenceSafetyPolicy | None = None) -> None:
        self.policy = policy or ReferenceSafetyPolicy()

    def assess(self, question: Question) -> SafetyAssessment:
        raw = question.metadata.get("a1_safety_signals")
        try:
            payload = dict(raw) if isinstance(raw, dict) else {}
            payload.setdefault("question_id", question.question_id)
            result = self.policy.assess(SafetyPolicyInput.model_validate(payload))
        except (TypeError, ValueError, ValidationError) as exc:
            return SafetyAssessment(
                decision=A5SafetyDecision.UNKNOWN,
                reason=f"safety_contract_invalid: {type(exc).__name__}",
                policy_version=self.policy.version,
            )

        decision_map = {
            A1SafetyDecision.ALLOW: A5SafetyDecision.ALLOW,
            A1SafetyDecision.DENY: A5SafetyDecision.DENY,
            A1SafetyDecision.UNKNOWN: A5SafetyDecision.UNKNOWN,
        }
        return SafetyAssessment(
            decision=decision_map[result.decision],
            reason="; ".join(result.reason_codes),
            policy_version=result.policy_version,
        )
