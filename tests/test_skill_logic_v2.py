from a5.domain.enums import ClaimCriticality, FreshnessState, UncertaintyLevel
from a5.domain.models import Claim, EvidenceRecord, EvidenceSpan, Question
from a5.runtime_config import load_runtime_config
from a5.skills.citation_audit import ClaimSplitter
from a5.skills.evidence_research import EvidenceResearchSkill


def test_evidence_research_produces_plan_and_empty_summary_without_fabrication() -> None:
    result = EvidenceResearchSkill().execute(
        Question(text="Which treatment evidence applies to the artificial fixture?")
    )
    assert result.question_type == "treatment_evidence"
    assert result.max_tool_calls == load_runtime_config().agent.max_tool_calls
    assert result.evidence_summary.evidence_count == 0
    assert result.evidence_summary.source_diversity is None
    assert result.evidence_summary.strongest_evidence_level is None
    assert result.evidence_summary.freshness_summary is FreshnessState.UNKNOWN


def test_evidence_summary_reports_sources_level_freshness_and_conflict() -> None:
    skill = EvidenceResearchSkill()
    records = [
        EvidenceRecord(
            id="E-A",
            content="Artificial A.",
            source_type="guideline",
            title="Mock A",
            retrieval_score=0.9,
            evidence_level="guideline",
            published_at="2026-07-01T00:00:00Z",
            conflicts_with_ids=["E-B"],
            mock=True,
        ),
        EvidenceRecord(
            id="E-B",
            content="Artificial B.",
            source_type="systematic_review",
            title="Mock B",
            retrieval_score=0.8,
            evidence_level="systematic_review",
            published_at="2026-06-01T00:00:00Z",
            conflicts_with_ids=["E-A"],
            mock=True,
        ),
    ]
    summary = skill.summarize(records, freshness_required=True)
    assert summary.evidence_count == 2
    assert summary.source_diversity == 1.0
    assert summary.strongest_evidence_level == "guideline"
    assert summary.freshness_summary is FreshnessState.FRESH
    assert summary.conflicts_detected is True


def test_claim_splitter_emits_atomic_claims_and_preserves_bindings() -> None:
    compound = Claim(
        claim_id="C1",
        run_id="RUN-X",
        text="Artificial fact A is present and artificial fact B is present.",
        criticality=ClaimCriticality.CRITICAL,
        evidence_ids=["E1"],
        evidence_span_ids=["S1"],
        uncertainty=UncertaintyLevel.LOW,
    )
    atomic = ClaimSplitter().split([compound])
    assert [claim.claim_id for claim in atomic] == ["C1.1", "C1.2"]
    assert [claim.text for claim in atomic] == [
        "Artificial fact A is present",
        "artificial fact B is present",
    ]
    assert all(claim.evidence_ids == ["E1"] for claim in atomic)
    assert all(claim.evidence_span_ids == ["S1"] for claim in atomic)


def test_claim_splitter_keeps_already_atomic_claim_stable() -> None:
    claim = Claim(
        claim_id="C2",
        text="One artificial fact",
        criticality=ClaimCriticality.CONTEXT,
    )
    assert ClaimSplitter().split([claim]) == [claim]
