from __future__ import annotations

from a5.domain.enums import SafetyStatus
from a5.domain.models import Question, SafetyAssessment


class DefaultSafetyPolicy:
    """TEMPORARY DEVELOPMENT POLICY; must be replaced by A1 rules.

    It deliberately does not invent medical safety rules. Tests/integrators may
    explicitly set metadata.safety_allowed=false to exercise refusal behavior.
    """

    version = "temporary-a1-safety-v0.1"

    def assess(self, question: Question) -> SafetyAssessment:
        explicitly_allowed = question.metadata.get("safety_allowed", True)
        if explicitly_allowed is False:
            return SafetyAssessment(
                status=SafetyStatus.REFUSED,
                reason="Question was explicitly rejected by the temporary policy input.",
                policy_version=self.version,
            )
        return SafetyAssessment(
            status=SafetyStatus.ALLOWED,
            reason="Allowed for development only; final A1 medical policy is pending.",
            policy_version=self.version,
        )
