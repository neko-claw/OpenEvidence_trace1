from a5.domain.enums import (
    ClaimCriticality,
    Decision,
    UncertaintyLevel,
    VerificationStatus,
)
from a5.domain.models import (
    Claim,
    EvidenceRecord,
    VerificationContext,
    VerificationResult,
)
from a5.skills.citation_audit import CitationAuditSkill


class StatusVerifier:
    def __init__(self, statuses: dict[str, VerificationStatus]) -> None:
        self.statuses = statuses

    def verify(self, claim, evidence, context):
        del evidence, context
        return VerificationResult(
            claim_id=claim.claim_id,
            status=self.statuses[claim.claim_id],
            evidence_ids=claim.evidence_ids,
            checked_evidence_ids=claim.evidence_ids,
            citation_valid=True,
            uncertainty=claim.uncertainty,
            verification_method="test-verifier",
            reasons=[] if self.statuses[claim.claim_id] is VerificationStatus.SUPPORTED else ["test failure"],
        )


def evidence() -> list[EvidenceRecord]:
    return [EvidenceRecord(id="E1", content="mock", source_type="mock", title="mock", mock=True)]


def claim(claim_id: str, criticality: ClaimCriticality) -> Claim:
    return Claim(
        claim_id=claim_id,
        text=f"Atomic {claim_id}",
        criticality=criticality,
        evidence_ids=["E1"],
        uncertainty=UncertaintyLevel.LOW,
    )


def test_citation_audit_release_recommendations() -> None:
    critical = claim("C1", ClaimCriticality.CRITICAL)
    important = claim("C2", ClaimCriticality.IMPORTANT)
    passed = CitationAuditSkill(StatusVerifier({"C1": VerificationStatus.SUPPORTED})).audit(
        [critical], evidence(), VerificationContext()
    )
    warned = CitationAuditSkill(
        StatusVerifier({"C1": VerificationStatus.SUPPORTED, "C2": VerificationStatus.INSUFFICIENT})
    ).audit([critical, important], evidence(), VerificationContext())
    refused = CitationAuditSkill(StatusVerifier({"C1": VerificationStatus.INSUFFICIENT})).audit(
        [critical], evidence(), VerificationContext()
    )
    assert passed.decision is Decision.PASS
    assert warned.decision is Decision.WARN
    assert warned.approved_claim_ids == ["C1"]
    assert refused.decision is Decision.REFUSE


def test_citation_audit_refuses_empty_inputs() -> None:
    report = CitationAuditSkill(StatusVerifier({})).audit([], [])
    assert report.decision is Decision.REFUSE
