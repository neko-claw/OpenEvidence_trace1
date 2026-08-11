from a5.domain.enums import ClaimCriticality, Decision, VerificationStatus
from a5.domain.models import Claim, EvidenceRecord, Question, VerificationResult
from a5.skills.citation_audit import CitationAuditSkill
from a5.skills.evidence_research import EvidenceResearchSkill


class StatusVerifier:
    def __init__(self, statuses: dict[str, VerificationStatus]) -> None:
        self.statuses = statuses

    def verify(self, claim, evidence):
        return VerificationResult(
            claim_id=claim.claim_id,
            status=self.statuses[claim.claim_id],
            checked_evidence_ids=claim.evidence_ids,
            reason="test verifier",
            verifier="StatusVerifier",
        )


def evidence() -> list[EvidenceRecord]:
    return [
        EvidenceRecord(
            id="E1",
            content="mock",
            source_type="mock",
            title="mock",
            mock=True,
        )
    ]


def claim(claim_id: str, criticality: ClaimCriticality) -> Claim:
    return Claim(
        claim_id=claim_id,
        text=f"Atomic {claim_id}",
        criticality=criticality,
        evidence_ids=["E1"],
    )


def test_evidence_research_uses_replaceable_temporary_config() -> None:
    result = EvidenceResearchSkill().plan(Question(text="Which treatment evidence applies?"))
    assert result.question_type == "treatment_evidence"
    assert result.search_plan.max_tool_calls == 3
    assert result.policy_version.startswith("temporary-a1")


def test_citation_audit_passes_supported_claims() -> None:
    claims = [claim("C1", ClaimCriticality.CRITICAL)]
    report = CitationAuditSkill(StatusVerifier({"C1": VerificationStatus.SUPPORTED})).audit(
        claims, evidence()
    )
    assert report.decision is Decision.PASS
    assert report.approved_claim_ids == ["C1"]


def test_citation_audit_warns_and_removes_noncritical_insufficient_claim() -> None:
    claims = [
        claim("C1", ClaimCriticality.CRITICAL),
        claim("C2", ClaimCriticality.IMPORTANT),
    ]
    verifier = StatusVerifier(
        {"C1": VerificationStatus.SUPPORTED, "C2": VerificationStatus.INSUFFICIENT}
    )
    report = CitationAuditSkill(verifier).audit(claims, evidence())
    assert report.decision is Decision.WARN
    assert report.approved_claim_ids == ["C1"]
    assert report.rejected_claim_ids == ["C2"]


def test_citation_audit_refuses_unsupported_critical_claim() -> None:
    claims = [claim("C1", ClaimCriticality.CRITICAL)]
    report = CitationAuditSkill(
        StatusVerifier({"C1": VerificationStatus.INSUFFICIENT})
    ).audit(claims, evidence())
    assert report.decision is Decision.REFUSE


def test_citation_audit_refuses_empty_evidence() -> None:
    report = CitationAuditSkill(StatusVerifier({})).audit([], [])
    assert report.decision is Decision.REFUSE
