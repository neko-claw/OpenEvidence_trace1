from __future__ import annotations

from datetime import datetime, timezone

from a5.domain.enums import ClaimCriticality, Decision, UncertaintyLevel, VerificationStatus
from a5.domain.models import (
    AgentPlan,
    CitationAuditReport,
    Claim,
    EvidenceRecord,
    EvidenceSpan,
    Question,
    SearchPlan,
)
from a5.generation.research_finalizer import ResearchAnswerFinalizer


def test_structured_answer_is_answer_first_and_keeps_claim_citations() -> None:
    evidence = EvidenceRecord(
        id="E1",
        title="Verified public article",
        content="Supported conclusion.",
        source_type="pubmed",
        published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        evidence_level="systematic_review",
        spans=[EvidenceSpan(span_id="S1", text="Supported conclusion.")],
    )
    claim = Claim(
        claim_id="C1",
        text="Supported conclusion.",
        criticality=ClaimCriticality.CRITICAL,
        evidence_ids=["E1"],
        evidence_span_ids=["S1"],
        uncertainty=UncertaintyLevel.LOW,
        decision=VerificationStatus.SUPPORTED,
    )
    plan = AgentPlan(
        question_type="comparative_effectiveness",
        selected_skill="evidence_research@test",
        search_plan=SearchPlan(
            queries=["query"],
            preferred_sources=["pubmed"],
            expected_evidence_types=["systematic_review"],
            max_tool_calls=1,
        ),
        policy_version="test",
    )
    answer = ResearchAnswerFinalizer().finalize_with_context(
        Decision.PASS,
        Question(text="哪种治疗证据更充分？"),
        plan,
        [claim],
        [evidence],
        CitationAuditReport(
            decision=Decision.PASS,
            approved_claim_ids=["C1"],
        ),
    )
    assert answer.structured is not None
    assert answer.structured.direct_answer == "Supported conclusion."
    assert answer.structured.direct_evidence_ids == ["E1"]
    assert answer.structured.findings[0].claim_ids == ["C1"]
    assert answer.structured.findings[0].evidence_ids == ["E1"]
    assert "系统综述" in answer.structured.evidence_profile[0]
    assert "未包含经正式指南" in answer.structured.uncertainties[1]


def test_structured_answer_cannot_publish_rejected_claim() -> None:
    claim = Claim(
        claim_id="C1",
        text="Rejected statement.",
        criticality=ClaimCriticality.CRITICAL,
        evidence_ids=["E1"],
        evidence_span_ids=["S1"],
        uncertainty=UncertaintyLevel.HIGH,
        decision=VerificationStatus.INSUFFICIENT,
    )
    answer = ResearchAnswerFinalizer().finalize_with_context(
        Decision.WARN,
        Question(text="问题"),
        None,
        [claim],
        [],
        CitationAuditReport(decision=Decision.WARN, rejected_claim_ids=["C1"]),
    )
    assert answer.structured is not None
    assert answer.structured.findings == []
    assert "Rejected statement" not in answer.text
