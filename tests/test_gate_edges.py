from datetime import date

from a5.adapters.default_safety_policy import DefaultFailClosedSafetyPolicy, FixtureSafetyPolicy
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.domain.enums import (
    ClaimCriticality,
    EvidenceIntegrityStatus,
    FreshnessState,
    MatchStatus,
    RecommendedAction,
    RetrievalScoreKind,
    RetrievalScoreScope,
    SafetyDecision,
    SufficiencyStatus,
    UncertaintyLevel,
    VerificationStatus,
)
from a5.domain.models import (
    Claim,
    EvidenceRecord,
    EvidenceSpan,
    Question,
    TextualSupportAssessment,
    VerificationContext,
)
from a5.gates.evidence_sufficiency import EvidenceSufficiencyGate
from a5.gates.evidence_integrity import EvidenceIntegrityGate
from a5.runtime_config import load_runtime_config


def evidence(
    evidence_id: str = "E1",
    *,
    source: str = "guideline",
    score: float | None = 0.9,
    level: str | None = "guideline",
    published: str | None = "2026-07-01T00:00:00Z",
    span_text: str = "Artificial fact is supported.",
    conflicts: list[str] | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        id=evidence_id,
        content=span_text,
        source_type=source,
        title=f"Mock {evidence_id}",
        retrieval_score=score,
        retrieval_score_kind=(RetrievalScoreKind.QUALITY if score is not None else RetrievalScoreKind.UNKNOWN),
        retrieval_score_scope=(RetrievalScoreScope.CROSS_QUERY if score is not None else RetrievalScoreScope.UNKNOWN),
        retrieval_score_calibrated=(True if score is not None else None),
        evidence_level=level,
        published_at=published,
        spans=[EvidenceSpan(span_id=f"S-{evidence_id}", text=span_text)],
        conflicts_with_ids=conflicts or [],
        mock=True,
    )


def claim(**updates) -> Claim:
    data = {
        "claim_id": "C1",
        "run_id": "RUN-X",
        "text": "Artificial fact is supported",
        "criticality": ClaimCriticality.CRITICAL,
        "evidence_ids": ["E1"],
        "evidence_span_ids": ["S-E1"],
        "uncertainty": UncertaintyLevel.LOW,
    }
    data.update(updates)
    return Claim(**data)


def test_gate0_unknown_and_deny_refuse_but_explicit_allow_continues() -> None:
    unknown = DefaultFailClosedSafetyPolicy().assess(Question(text="fixture"))
    denied = FixtureSafetyPolicy().assess(
        Question(text="fixture", metadata={"mock_safety_decision": "DENY"})
    )
    allowed = FixtureSafetyPolicy().assess(
        Question(text="fixture", metadata={"mock_safety_decision": "ALLOW"})
    )
    assert unknown.decision is SafetyDecision.UNKNOWN
    assert denied.decision is SafetyDecision.DENY
    assert allowed.decision is SafetyDecision.ALLOW


def test_gate2_covers_low_count_score_source_diversity_and_missing_metrics() -> None:
    gate = EvidenceSufficiencyGate(load_runtime_config().gates.gate2)
    result = gate.evaluate(
        [evidence(score=None, level=None, published=None)],
        freshness_required=True,
        budget_remaining=1,
        as_of_date=date(2026, 8, 11),
    )
    assert result.status is SufficiencyStatus.INSUFFICIENT
    assert result.recommended_action is RecommendedAction.RETRY
    assert result.metrics.top_score is None
    assert result.metrics.strongest_evidence_level is None
    assert result.metrics.freshness_state is FreshnessState.UNKNOWN
    joined = " ".join(result.reasons)
    assert "candidate_count" in joined
    assert "quality score UNKNOWN" in joined
    assert "source coverage" in joined


def test_gate2_sufficient_and_conflicted_paths() -> None:
    gate = EvidenceSufficiencyGate(load_runtime_config().gates.gate2)
    good = [
        evidence("E1", source="guideline", level="guideline"),
        evidence("E2", source="systematic_review", level="systematic_review"),
    ]
    sufficient = gate.evaluate(
        good, freshness_required=True, budget_remaining=1, as_of_date=date(2026, 8, 11)
    )
    assert sufficient.status is SufficiencyStatus.SUFFICIENT
    assert sufficient.recommended_action is RecommendedAction.CONTINUE
    conflicted = gate.evaluate(
        [
            evidence("E1", source="guideline", conflicts=["E2"]),
            evidence("E2", source="systematic_review", level="systematic_review"),
        ],
        freshness_required=True,
        budget_remaining=1,
        as_of_date=date(2026, 8, 11),
    )
    assert conflicted.status is SufficiencyStatus.CONFLICTED
    assert conflicted.metrics.conflict_count == 1
    assert conflicted.recommended_action is RecommendedAction.REFUSE


def test_gate2_budget_exhaustion_recommends_refuse() -> None:
    result = EvidenceSufficiencyGate(load_runtime_config().gates.gate2).evaluate(
        [], freshness_required=True, budget_remaining=0, as_of_date=date(2026, 8, 11)
    )
    assert result.recommended_action is RecommendedAction.REFUSE
    assert any("budget_exhausted" in reason for reason in result.reasons)


def test_gate1_is_fail_closed_and_mock_requires_explicit_fixture_mode() -> None:
    config = load_runtime_config().gates.gate1
    strict = EvidenceIntegrityGate(config).evaluate([evidence()])
    fixture = EvidenceIntegrityGate(config, allow_mock=True).evaluate([evidence()])
    assert strict.status is EvidenceIntegrityStatus.REJECTED
    assert fixture.status is EvidenceIntegrityStatus.ELIGIBLE


def test_gate1_production_provenance_requires_marker_and_fields() -> None:
    config = load_runtime_config().gates.gate1
    record = evidence()
    record.mock = False
    unknown = EvidenceIntegrityGate(config).evaluate([record])
    assert unknown.status is EvidenceIntegrityStatus.UNKNOWN
    record.source_metadata.update(
        {
            "stable_id": "source-native-id",
            "url": "https://example.invalid/source",
            "fetched_at": "2026-08-11T00:00:00Z",
            "content_hash": "a" * 64,
            "source_integrity": "a2_mcp_normalized",
        }
    )
    eligible = EvidenceIntegrityGate(config).evaluate([record])
    assert eligible.status is EvidenceIntegrityStatus.ELIGIBLE


def test_gate2_does_not_treat_query_local_rerank_score_as_quality_probability() -> None:
    record = evidence(score=0.99)
    record.retrieval_score_kind = RetrievalScoreKind.RANKING
    record.retrieval_score_scope = RetrievalScoreScope.QUERY_LOCAL
    record.retrieval_score_calibrated = False
    result = EvidenceSufficiencyGate(load_runtime_config().gates.gate2).evaluate(
        [record, evidence("E2", source="systematic_review")],
        freshness_required=False,
        budget_remaining=0,
        as_of_date=date(2026, 8, 11),
    )
    assert result.metrics.top_ranking_score == 0.99
    assert result.metrics.top_score == 0.9
    assert result.metrics.usable_quality_score_count == 1


def test_gate2_all_uncalibrated_scores_remain_unknown() -> None:
    records = [
        evidence("E1", source="guideline", score=0.99),
        evidence("E2", source="systematic_review", score=0.98),
    ]
    for record in records:
        record.retrieval_score_kind = RetrievalScoreKind.RANKING
        record.retrieval_score_scope = RetrievalScoreScope.QUERY_LOCAL
        record.retrieval_score_calibrated = False
    result = EvidenceSufficiencyGate(load_runtime_config().gates.gate2).evaluate(
        records,
        freshness_required=False,
        budget_remaining=0,
        as_of_date=date(2026, 8, 11),
    )
    assert result.status is SufficiencyStatus.INSUFFICIENT
    assert result.metrics.top_score is None
    assert result.metrics.top_ranking_score == 0.99


def test_gate5_support_requires_whitelisted_span_and_textual_entailment() -> None:
    result = RuleBasedClaimVerifier().verify(
        claim(), [evidence()], VerificationContext(freshness_required=True, run_date=date(2026, 8, 11))
    )
    assert result.status is VerificationStatus.SUPPORTED
    assert result.citation_valid is True
    assert result.span_check is MatchStatus.MATCH
    assert result.entailment_score == 1.0


def test_gate5_illegal_evidence_and_missing_span_never_support() -> None:
    verifier = RuleBasedClaimVerifier()
    illegal = verifier.verify(
        claim(evidence_ids=["E999"]), [evidence()], VerificationContext()
    )
    missing_span = verifier.verify(
        claim(evidence_span_ids=[]), [evidence()], VerificationContext()
    )
    assert illegal.status is VerificationStatus.INSUFFICIENT
    assert illegal.illegal_evidence_ids == ["E999"]
    assert missing_span.status is VerificationStatus.INSUFFICIENT
    assert missing_span.span_check is MatchStatus.UNKNOWN


def test_gate5_pico_and_time_mismatch_are_explainable() -> None:
    verifier = RuleBasedClaimVerifier()
    record = evidence(published=None)
    record.population = "different population"
    result = verifier.verify(
        claim(population="expected population"),
        [record],
        VerificationContext(freshness_required=True),
    )
    assert result.status is VerificationStatus.INSUFFICIENT
    assert result.population_match is MatchStatus.MISMATCH
    assert result.time_match is MatchStatus.UNKNOWN
    assert "pico_mismatch" in result.reason
    assert "time_mismatch" in result.reason


def test_gate5_claim_as_of_date_rejects_future_evidence() -> None:
    result = RuleBasedClaimVerifier().verify(
        claim(as_of_date=date(2025, 1, 1)),
        [evidence(published="2026-07-01T00:00:00Z")],
        VerificationContext(freshness_required=False),
    )
    assert result.time_match is MatchStatus.MISMATCH
    assert result.status is VerificationStatus.INSUFFICIENT


def test_gate5_unknown_entailment_and_fixture_gold_labels_do_not_become_supported() -> None:
    record = evidence(span_text="Different fixture text.")
    record.source_metadata["supports_claim_ids"] = ["C1"]
    result = RuleBasedClaimVerifier().verify(claim(), [record], VerificationContext())
    assert result.status is VerificationStatus.INSUFFICIENT
    assert result.entailment_score is None


class ContradictingEvaluator:
    def evaluate(self, claim, evidence):
        return TextualSupportAssessment(
            status=VerificationStatus.CONTRADICTED,
            entailment_score=0.0,
            method="test-contradiction",
            reason="contradicted_claim: test evaluator",
        )


class AlwaysSupportingEvaluator:
    def evaluate(self, claim, evidence):
        return TextualSupportAssessment(
            status=VerificationStatus.SUPPORTED,
            entailment_score=1.0,
            method="test-support",
            reason="textual_support: injected test support",
        )


def test_gate5_textual_support_is_replaceable_and_contradiction_blocks() -> None:
    result = RuleBasedClaimVerifier(textual_support=ContradictingEvaluator()).verify(
        claim(), [evidence()], VerificationContext()
    )
    assert result.status is VerificationStatus.CONTRADICTED
    assert result.verification_method == "test-contradiction"


def test_gate5_numeric_mismatch_blocks_even_when_semantic_extension_says_supported() -> None:
    record = evidence(span_text="Artificial dose is 20 mg.")
    result = RuleBasedClaimVerifier(textual_support=AlwaysSupportingEvaluator()).verify(
        claim(text="Artificial dose is 10 mg"), [record], VerificationContext()
    )
    assert result.numeric_match is MatchStatus.MISMATCH
    assert result.unit_match is MatchStatus.MATCH
    assert result.status is VerificationStatus.INSUFFICIENT
    assert "numeric_mismatch" in result.reason
