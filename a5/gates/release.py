from __future__ import annotations

from collections.abc import Sequence

from a5.domain.enums import (
    ClaimCriticality,
    Decision,
    EvidenceIntegrityStatus,
    SafetyDecision,
    SufficiencyStatus,
    VerificationStatus,
)
from a5.domain.models import (
    Claim,
    EvidenceIntegrityResult,
    EvidenceSufficiencyResult,
    SafetyAssessment,
    VerificationResult,
)
from a5.runtime_config import Gate6Config


class ReleaseGate:
    def __init__(self, config: Gate6Config) -> None:
        self.config = config

    def decide(
        self,
        *,
        safety: SafetyAssessment,
        integrity: EvidenceIntegrityResult | None,
        sufficiency: EvidenceSufficiencyResult | None,
        claims: Sequence[Claim],
        results: Sequence[VerificationResult],
    ) -> tuple[Decision, list[str]]:
        reasons: list[str] = []
        if safety.decision is not SafetyDecision.ALLOW:
            return Decision.REFUSE, [f"safety_denied: Gate0={safety.decision.value}"]
        if integrity is not None and integrity.status is EvidenceIntegrityStatus.REJECTED:
            return Decision.REFUSE, list(dict.fromkeys(integrity.reasons))
        if sufficiency is None or sufficiency.status is not SufficiencyStatus.SUFFICIENT:
            details = sufficiency.reasons if sufficiency else ["Gate2 result missing"]
            return Decision.REFUSE, list(dict.fromkeys(details))
        if integrity is None or integrity.status is not EvidenceIntegrityStatus.ELIGIBLE:
            details = integrity.reasons if integrity else ["Gate1 result missing"]
            return Decision.REFUSE, list(dict.fromkeys(details))
        if not claims:
            return Decision.REFUSE, ["unsupported_claim: no atomic claims"]

        claims_by_id = {claim.claim_id: claim for claim in claims}
        results_by_id = {result.claim_id: result for result in results}
        for claim in claims:
            result = results_by_id.get(claim.claim_id)
            if result is None:
                reasons.append(f"unsupported_claim: missing verification for {claim.claim_id}")
                continue
            if result.illegal_evidence_ids:
                reasons.append(f"illegal_citation: {claim.claim_id}")
            if claim.criticality is ClaimCriticality.CRITICAL:
                if result.status is not VerificationStatus.SUPPORTED:
                    reasons.append(f"unsupported_claim: critical {claim.claim_id}")
                if claim.uncertainty not in self.config.critical_allowed_uncertainty:
                    reasons.append(f"high_uncertainty: critical {claim.claim_id}")
                if result.conflict_ids:
                    reasons.append(f"retrieval_conflict: critical {claim.claim_id}")
        critical_reasons = [
            reason
            for reason in reasons
            if reason.startswith(("illegal_citation", "unsupported_claim", "high_uncertainty", "retrieval_conflict"))
        ]
        if critical_reasons:
            return Decision.REFUSE, list(dict.fromkeys(reasons))

        noncritical_failures = [
            result
            for result in results
            if claims_by_id[result.claim_id].criticality is not ClaimCriticality.CRITICAL
            and result.status is not VerificationStatus.SUPPORTED
        ]
        if noncritical_failures:
            return Decision.WARN, [
                "unsupported_claim: non-critical claims were removed after Gate5"
            ]
        return Decision.PASS, []
