from __future__ import annotations

from datetime import date, datetime, timezone

from a5.domain.enums import FreshnessState, SufficiencyStatus
from a5.domain.models import AgentPlan, EvidenceRecord, EvidenceSpan, Question, SearchPlan
from a5.gates.research_sufficiency import ResearchEvidenceSufficiencyGate
from a5.adapters.rule_based_claim_verifier import ExactSpanTextualSupportEvaluator
from a5.domain.enums import ClaimCriticality, UncertaintyLevel, VerificationStatus
from a5.domain.models import Claim
from a5.runtime_config import load_runtime_config
from a1.ports import SafetyClassificationRequest
from backend.extractive_claims import ExtractiveClaimGenerator
from backend.research_planner import PublicEvidenceResearchSkill
from backend.research_profile import load_research_profile
from backend.research_safety import ConservativeResearchSafetyClassifier
from deployment.track1_backend import build_service


def _record(identifier: str, source: str, score: float, text: str) -> EvidenceRecord:
    return EvidenceRecord(
        id=identifier,
        title=f"Public record {identifier}",
        content=text,
        source_type=source,
        source_metadata={"ranking_score": score},
        published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        evidence_level="systematic_review",
        spans=[EvidenceSpan(span_id=f"{identifier}-S1", text=text)],
    )


def test_research_safety_is_topic_limited_and_fail_closed() -> None:
    classifier = ConservativeResearchSafetyClassifier()
    allowed = classifier.classify(SafetyClassificationRequest(
        question_id="Q1", text="高血压患者的血压控制目标有哪些最新证据？"
    ))
    denied = classifier.classify(SafetyClassificationRequest(
        question_id="Q2", text="高血压患者今晚药该吃多少毫克"
    ))
    outside = classifier.classify(SafetyClassificationRequest(
        question_id="Q3", text="偏头痛有哪些治疗方法？"
    ))
    assert allowed.topic.value == "hypertension"
    assert denied.personalized_prescribing_or_dose_change is True
    assert outside.topic.value == "other"


def test_research_scope_includes_cardio_cerebrovascular_and_diabetes() -> None:
    classifier = ConservativeResearchSafetyClassifier()
    cases = {
        "冠心病二级预防有哪些指南证据？": "cardiovascular",
        "缺血性脑卒中复发预防有哪些系统综述？": "cerebrovascular",
        "2型糖尿病患者心血管结局有哪些最新试验？": "diabetes",
    }
    for index, (text, topic) in enumerate(cases.items(), start=1):
        result = classifier.classify(
            SafetyClassificationRequest(question_id=f"Q-{index}", text=text)
        )
        assert result.topic.value == topic


def test_research_planner_translates_intent_into_public_source_queries() -> None:
    plan = PublicEvidenceResearchSkill(load_runtime_config()).plan(
        Question(text="慢性肾病高血压患者的最新血压控制目标是什么？")
    )
    assert plan.question_type == "guideline_treatment"
    assert any("chronic kidney disease" in query for query in plan.search_plan.queries)
    assert plan.search_plan.freshness_required is True
    assert plan.search_plan.preferred_sources[:2] == ["current_guideline", "pubmed_review"]


def test_research_planner_routes_trials_and_comparative_questions() -> None:
    skill = PublicEvidenceResearchSkill(load_runtime_config())
    trial = skill.plan(Question(text="2型糖尿病心血管结局有哪些最新临床试验？"))
    comparison = skill.plan(Question(text="房颤卒中预防中两种治疗的疗效和安全性如何比较？"))
    assert trial.question_type == "latest_research_trial"
    assert trial.search_plan.preferred_sources[0] == "clinicaltrials_record"
    assert "diabetes mellitus" in trial.search_plan.queries[0]
    assert comparison.question_type == "comparative_effectiveness"
    assert "atrial fibrillation" in comparison.search_plan.queries[0]


def test_research_gate_uses_balanced_source_diversity_without_fake_quality() -> None:
    gate = ResearchEvidenceSufficiencyGate(load_research_profile().retrieval)
    records = [
        _record("E1", "pubmed", 0.92, "A complete supported recommendation sentence."),
        _record("E2", "europe_pmc", 0.81, "A second complete supported recommendation sentence."),
        _record("E3", "pubmed", 0.76, "A third complete supported recommendation sentence."),
    ]
    result = gate.evaluate(
        records, freshness_required=True, budget_remaining=1, as_of_date=date(2026, 8, 12)
    )
    assert result.status is SufficiencyStatus.SUFFICIENT
    assert result.metrics.top_score is None
    assert result.metrics.top_ranking_score == 0.92
    assert result.metrics.source_diversity and result.metrics.source_diversity > 0.4
    assert result.metrics.freshness_state is FreshnessState.FRESH


def test_extractive_generator_emits_complete_pre_atomic_sentences() -> None:
    text = (
        "BACKGROUND: We evaluated trends in blood pressure treatment. "
        "If blood pressure remains above the target, pharmacotherapy is advised."
    )
    record = _record("E1", "pubmed", 0.9, text)
    generator = ExtractiveClaimGenerator(max_claims=1, min_chars=20, max_chars=300)
    plan = AgentPlan(
        question_type="guideline_treatment",
        selected_skill="evidence_research@test",
        search_plan=SearchPlan(
            queries=["hypertension target recommendation"],
            preferred_sources=["pubmed"],
            expected_evidence_types=["guideline"],
            max_tool_calls=1,
        ),
        policy_version="test",
    )
    claims = generator.generate(Question(text="target?"), [record], plan, "RUN-1")
    assert len(claims) == 1
    assert claims[0].text == "If blood pressure remains above the target, pharmacotherapy is advised."
    assert claims[0].text in record.spans[0].text


def test_extractive_generator_filters_methods_and_respects_intervention_focus() -> None:
    irrelevant = _record(
        "E1", "pubmed", 0.99,
        "A random-effects meta-analysis was used. Another therapy reduced cholesterol significantly.",
    )
    relevant = _record(
        "E2", "europe_pmc", 0.80,
        "Statin therapy reduced the reported cardiovascular outcome compared with control.",
    )
    generator = ExtractiveClaimGenerator(max_claims=2, min_chars=20, max_chars=300)
    plan = AgentPlan(
        question_type="treatment_evidence",
        selected_skill="evidence_research@test",
        search_plan=SearchPlan(
            queries=["dyslipidemia statin systematic review"],
            preferred_sources=["pubmed", "europe_pmc"],
            expected_evidence_types=["systematic_review"],
            max_tool_calls=2,
        ),
        policy_version="test",
    )
    claims = generator.generate(Question(text="statin?"), [irrelevant, relevant], plan, "RUN-2")
    assert [claim.text for claim in claims] == [
        "Statin therapy reduced the reported cardiovascular outcome compared with control."
    ]


def test_comparative_generator_rejects_background_and_requires_both_interventions() -> None:
    background = _record(
        "E1", "pubmed", 0.99,
        "Atrial fibrillation is a major cause of ischemic stroke. "
        "DOACs have attractive pharmacologic profiles for patients.",
    )
    answer = _record(
        "E2", "europe_pmc", 0.85,
        "In atrial fibrillation, DOACs were associated with a lower recurrent stroke risk "
        "compared with Warfarin.",
    )
    generator = ExtractiveClaimGenerator(max_claims=3, min_chars=20, max_chars=300)
    plan = AgentPlan(
        question_type="comparative_effectiveness",
        selected_skill="evidence_research@test",
        search_plan=SearchPlan(
            queries=["atrial fibrillation stroke DOAC Warfarin comparative effectiveness"],
            preferred_sources=["pubmed", "europe_pmc"],
            expected_evidence_types=["systematic_review"],
            max_tool_calls=2,
        ),
        policy_version="test",
    )
    claims = generator.generate(
        Question(text="房颤卒中预防中 DOAC 与华法林如何比较？"),
        [background, answer],
        plan,
        "RUN-3",
    )
    assert [claim.text for claim in claims] == [
        "In atrial fibrillation, DOACs were associated with a lower recurrent stroke risk "
        "compared with Warfarin."
    ]


def test_research_run_records_effective_profile_and_generation_mode(monkeypatch) -> None:
    from backend.structured_transport import OllamaStructuredTransport

    monkeypatch.setattr(OllamaStructuredTransport, "available", lambda self, model: False)
    dependencies = build_service("research")
    assert dependencies.mode == "research"
    assert dependencies.dependencies is not None
    workflow = dependencies.dependencies.workflow
    extension = workflow._runtime_snapshot_extension
    assert extension["research_profile"]["profile_version"] == "public-evidence-research-v0.2.0"
    assert extension["effective_generation_mode"] == "exact_span_extractive"
    assert extension["ranking_semantics"] == "query_local_not_calibrated_quality"


def test_exact_span_verifier_ignores_source_html_markup() -> None:
    record = _record("E1", "europe_pmc", 0.9, "<h4>Aim</h4>This sentence is supported.")
    claim = Claim(
        claim_id="C1",
        text="Aim This sentence is supported.",
        criticality=ClaimCriticality.CRITICAL,
        evidence_ids=["E1"],
        evidence_span_ids=["E1-S1"],
        uncertainty=UncertaintyLevel.LOW,
    )
    result = ExactSpanTextualSupportEvaluator().evaluate(claim, [record])
    assert result.status is VerificationStatus.SUPPORTED
