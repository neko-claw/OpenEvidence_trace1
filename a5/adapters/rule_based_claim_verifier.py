from __future__ import annotations

from collections.abc import Sequence

from a5.domain.enums import VerificationStatus
from a5.domain.models import Claim, EvidenceRecord, VerificationResult


class RuleBasedClaimVerifier:
    """Mechanical development verifier, not a medical semantic verifier.

    It enforces citation presence/whitelisting and consumes explicit rule markers
    from mock metadata. Real support/contradiction inference belongs in a future
    LLM, NLI, or medical verifier implementing the same port.
    """

    name = "rule_based@v0.1"

    def verify(
        self,
        claim: Claim,
        evidence: Sequence[EvidenceRecord],
    ) -> VerificationResult:
        evidence_by_id = {record.id: record for record in evidence}
        whitelist = set(evidence_by_id)
        illegal_ids = sorted(set(claim.evidence_ids) - whitelist)

        if not claim.evidence_ids:
            return self._result(
                claim,
                VerificationStatus.INSUFFICIENT,
                [],
                [],
                "Claim has no evidence IDs.",
            )
        if illegal_ids:
            return self._result(
                claim,
                VerificationStatus.INSUFFICIENT,
                [],
                illegal_ids,
                "Claim cites evidence outside the retrieved-evidence whitelist.",
            )

        cited = [evidence_by_id[evidence_id] for evidence_id in claim.evidence_ids]
        supports = any(
            claim.claim_id in record.source_metadata.get("supports_claim_ids", [])
            for record in cited
        )
        contradicts = any(
            claim.claim_id in record.source_metadata.get("contradicts_claim_ids", [])
            for record in cited
        )

        if supports and contradicts:
            status = VerificationStatus.CONTRADICTED
            reason = "Explicit support and contradiction markers conflict; failing closed."
        elif contradicts:
            status = VerificationStatus.CONTRADICTED
            reason = "An explicit contradiction marker was found."
        elif supports:
            status = VerificationStatus.SUPPORTED
            reason = "An explicit rule-level support marker was found."
        else:
            status = VerificationStatus.INSUFFICIENT
            reason = "No explicit rule-level support marker was found."
        return self._result(claim, status, claim.evidence_ids, [], reason)

    def _result(
        self,
        claim: Claim,
        status: VerificationStatus,
        checked_ids: list[str],
        illegal_ids: list[str],
        reason: str,
    ) -> VerificationResult:
        return VerificationResult(
            claim_id=claim.claim_id,
            status=status,
            checked_evidence_ids=checked_ids,
            illegal_evidence_ids=illegal_ids,
            reason=reason,
            verifier=self.name,
        )
