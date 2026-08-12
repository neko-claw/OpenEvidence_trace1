from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from a1.models import SafetyDecision as A1SafetyDecision
from a1.models import SafetyPolicyInput, SafetyPolicyOutput
from a1.policy import ReferenceSafetyPolicy
from a1.ports.safety_classifier import SafetyClassificationRequest, SafetySignalClassifier
from a5.domain.enums import SafetyDecision as A5SafetyDecision
from a5.domain.models import Question, SafetyAssessment


class SafetyPolicyEvaluator(Protocol):
    version: str

    def assess(self, policy_input: SafetyPolicyInput) -> object: ...


class A1SafetyPolicyAdapter:
    """Adapt normalized A1 Gate0 signals to the A5 ``SafetyPolicy`` port.

    No free-text safety classification happens here. The normalized payload is
    expected at ``question.metadata['a1_safety_signals']``. A reviewed A1 text
    classifier can be injected for ordinary questions. Missing classifiers,
    missing fields, classifier failures, and invalid payloads are all mapped to
    UNKNOWN, preserving A5's fail-closed behavior.
    """

    def __init__(
        self,
        policy: SafetyPolicyEvaluator | None = None,
        *,
        classifier: SafetySignalClassifier | None = None,
    ) -> None:
        self.policy = policy or ReferenceSafetyPolicy()
        self.classifier = classifier

    def assess(self, question: Question) -> SafetyAssessment:
        raw = question.metadata.get("a1_safety_signals")
        try:
            if isinstance(raw, Mapping):
                payload = dict(raw)
            elif self.classifier is not None:
                classified = self.classifier.classify(
                    SafetyClassificationRequest(
                        question_id=question.question_id,
                        text=question.text,
                    )
                )
                if isinstance(classified, SafetyPolicyInput):
                    payload = classified.model_dump(mode="python")
                elif isinstance(classified, Mapping):
                    payload = dict(classified)
                else:
                    raise TypeError("classifier returned an unsupported signal payload")
            else:
                payload = {}
            payload.setdefault("question_id", question.question_id)
            result = SafetyPolicyOutput.model_validate(
                self.policy.assess(SafetyPolicyInput.model_validate(payload))
            )
        except Exception as exc:
            return SafetyAssessment(
                decision=A5SafetyDecision.UNKNOWN,
                reason=f"safety_contract_invalid: {type(exc).__name__}",
                policy_version=self._effective_version(self.policy.version),
            )

        decision_map = {
            A1SafetyDecision.ALLOW: A5SafetyDecision.ALLOW,
            A1SafetyDecision.DENY: A5SafetyDecision.DENY,
            A1SafetyDecision.UNKNOWN: A5SafetyDecision.UNKNOWN,
        }
        return SafetyAssessment(
            decision=decision_map[result.decision],
            reason="; ".join(result.reason_codes),
            policy_version=self._effective_version(result.policy_version),
        )

    def _effective_version(self, policy_version: str) -> str:
        classifier_version = getattr(self.classifier, "version", None)
        if isinstance(classifier_version, str) and classifier_version:
            return f"{policy_version}+{classifier_version}"
        return policy_version
