from __future__ import annotations

from collections.abc import Sequence

from a5.domain.enums import ClaimCriticality, Decision, VerificationStatus
from a5.domain.models import CitationAuditReport, Claim, EvidenceRecord, VerificationResult
from a5.ports.claim_verifier import ClaimVerifier


class CitationAuditSkill:
    name = "citation_audit"
    version = "0.1"

    def __init__(self, verifier: ClaimVerifier) -> None:
        self._verifier = verifier

    @property
    def identifier(self) -> str:
        return f"{self.name}@v{self.version}"

    def audit(
        self,
        claims: Sequence[Claim],
        evidence: Sequence[EvidenceRecord],
    ) -> CitationAuditReport:
        if not evidence:
            return CitationAuditReport(
                decision=Decision.REFUSE,
                rejected_claim_ids=[claim.claim_id for claim in claims],
                reasons=["No valid evidence was retrieved."],
            )
        if not claims:
            return CitationAuditReport(
                decision=Decision.REFUSE,
                reasons=["No verifiable claims were generated."],
            )

        results = [self._verifier.verify(claim, evidence) for claim in claims]
        claims_by_id = {claim.claim_id: claim for claim in claims}
        illegal_ids = {
            evidence_id
            for result in results
            for evidence_id in result.illegal_evidence_ids
        }
        critical_failures = [
            result
            for result in results
            if claims_by_id[result.claim_id].criticality is ClaimCriticality.CRITICAL
            and result.status is not VerificationStatus.SUPPORTED
        ]

        reasons: list[str] = []
        if illegal_ids:
            reasons.append(f"Illegal evidence IDs: {', '.join(sorted(illegal_ids))}.")
        if critical_failures:
            reasons.append(
                "Critical claims without unambiguous support: "
                + ", ".join(result.claim_id for result in critical_failures)
                + "."
            )

        if illegal_ids or critical_failures:
            decision = Decision.REFUSE
        elif any(result.status is not VerificationStatus.SUPPORTED for result in results):
            decision = Decision.WARN
            reasons.append("One or more non-critical claims were removed after verification.")
        else:
            decision = Decision.PASS

        approved = [
            result.claim_id
            for result in results
            if result.status is VerificationStatus.SUPPORTED
            and not result.illegal_evidence_ids
        ]
        rejected = [claim.claim_id for claim in claims if claim.claim_id not in approved]
        return CitationAuditReport(
            decision=decision,
            verification_results=results,
            approved_claim_ids=approved,
            rejected_claim_ids=rejected,
            reasons=reasons,
        )
