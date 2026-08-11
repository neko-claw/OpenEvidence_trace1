from __future__ import annotations

from pathlib import Path

import yaml

from a1.models import (
    Decision,
    RetrievalTerminationInput,
    RetrievalTerminationOutput,
    SafetyDecision,
    SafetyPolicyInput,
    SafetyPolicyOutput,
    SpecialPopulation,
    TerminationAction,
    TerminationPolicyAsset,
    TopicScope,
)


POLICY_VERSION = "a1-safety-v0.2"


class ReferenceSafetyPolicy:
    """Deterministic A1 Gate0 reference policy over normalized signals.

    This is a contract/reference evaluator, not a medical NLP classifier. It
    never guesses missing signals and therefore cannot silently ALLOW an
    unclassified question.
    """

    version = POLICY_VERSION

    def assess(self, policy_input: SafetyPolicyInput) -> SafetyPolicyOutput:
        matched: list[str] = []
        reasons: list[str] = []

        deny_flags = (
            (policy_input.acute_emergency, "G0_ACUTE_EMERGENCY", "safety_emergency"),
            (policy_input.personal_diagnosis, "G0_PERSONAL_DIAGNOSIS", "safety_personal_diagnosis"),
            (
                policy_input.personalized_prescribing_or_dose_change,
                "G0_PERSONALIZED_PRESCRIBING",
                "safety_personalized_prescribing",
            ),
            (
                policy_input.prompt_injection_or_fabricated_reference,
                "G0_INTEGRITY_ATTACK",
                "safety_integrity_attack",
            ),
            (
                policy_input.identifiable_personal_data,
                "G0_IDENTIFIABLE_PERSONAL_DATA",
                "safety_identifiable_data",
            ),
        )
        for enabled, rule, reason in deny_flags:
            if enabled is True:
                matched.append(rule)
                reasons.append(reason)

        if policy_input.topic is TopicScope.OTHER:
            matched.append("G0_OUTSIDE_TOPIC_SCOPE")
            reasons.append("safety_outside_topic_scope")
        if policy_input.special_population in {
            SpecialPopulation.PREGNANCY,
            SpecialPopulation.PEDIATRIC,
            SpecialPopulation.OTHER,
        }:
            matched.append("G0_SPECIAL_POPULATION")
            reasons.append("safety_special_population_route_unavailable")

        if reasons:
            return SafetyPolicyOutput(
                decision=SafetyDecision.DENY,
                policy_version=self.version,
                reason_codes=reasons,
                matched_rules=matched,
                termination_action=TerminationAction.REFUSE,
                user_message_key=(
                    "gate0.emergency" if "safety_emergency" in reasons else "gate0.out_of_scope"
                ),
            )

        required_flags = (
            policy_input.acute_emergency,
            policy_input.personal_diagnosis,
            policy_input.personalized_prescribing_or_dose_change,
            policy_input.prompt_injection_or_fabricated_reference,
            policy_input.identifiable_personal_data,
        )
        unknown = (
            any(value is None for value in required_flags)
            or policy_input.topic is TopicScope.UNKNOWN
            or policy_input.special_population is SpecialPopulation.UNKNOWN
        )
        if unknown:
            return SafetyPolicyOutput(
                decision=SafetyDecision.UNKNOWN,
                policy_version=self.version,
                reason_codes=["safety_signals_incomplete"],
                matched_rules=["G0_FAIL_CLOSED_UNKNOWN"],
                termination_action=TerminationAction.REFUSE,
                user_message_key="gate0.unclassified",
            )

        return SafetyPolicyOutput(
            decision=SafetyDecision.ALLOW,
            policy_version=self.version,
            reason_codes=["safety_scope_allowed"],
            matched_rules=["G0_ALLOWED_SCOPE"],
            termination_action=TerminationAction.CONTINUE,
            user_message_key="gate0.allowed",
        )


def evaluate_retrieval_termination(
    state: RetrievalTerminationInput,
) -> RetrievalTerminationOutput:
    """Apply the A1 Gate2 termination precedence without doing retrieval."""

    if state.unresolved_conflict:
        return RetrievalTerminationOutput(
            action=TerminationAction.REFUSE,
            decision=Decision.REFUSE,
            reason_codes=["retrieval_conflict_unresolved"],
        )
    if state.evidence_sufficient is True:
        return RetrievalTerminationOutput(
            action=TerminationAction.CONTINUE,
            reason_codes=["retrieval_sufficient"],
        )
    if not state.evidence_present and state.tool_budget_exhausted:
        return RetrievalTerminationOutput(
            action=TerminationAction.REFUSE,
            decision=Decision.REFUSE,
            reason_codes=["no_eligible_evidence", "budget_exhausted"],
        )
    if state.tool_budget_exhausted:
        return RetrievalTerminationOutput(
            action=TerminationAction.REFUSE,
            decision=Decision.REFUSE,
            reason_codes=["retrieval_insufficient", "budget_exhausted"],
        )
    if state.required_source_type_missing:
        return RetrievalTerminationOutput(
            action=TerminationAction.RETRY,
            reason_codes=["required_source_type_missing"],
        )
    return RetrievalTerminationOutput(
        action=TerminationAction.RETRY,
        reason_codes=[
            "retrieval_quality_unknown"
            if state.evidence_sufficient is None
            else "retrieval_insufficient"
        ],
    )


def load_termination_policy(path: str | Path) -> TerminationPolicyAsset:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return TerminationPolicyAsset.model_validate(payload)
