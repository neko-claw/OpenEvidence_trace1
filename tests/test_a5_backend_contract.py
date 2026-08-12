from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from a5.adapters.openai_compatible_claim_generator import (
    ClaimGenerationError,
    OpenAICompatibleClaimGenerator,
)
from a5.adapters.rule_based_claim_verifier import ExactSpanTextualSupportEvaluator
from a5.adapters.semantic_claim_verifier import (
    CompositeTextualSupportEvaluator,
    OpenAICompatibleSemanticEvaluator,
)
from a5.bootstrap import build_demo_workflow
from a5.domain.enums import Decision, VerificationStatus, WorkflowState
from a5.domain.models import AgentPlan, AgentRun, AgentRunView, EvidenceRecord, Question, SearchPlan
from a5.facade import answer_text, to_ui_view
from a5.gates.evidence_sufficiency import EvidenceSufficiencyGate
from a5.runtime_config import load_runtime_config
from a5.skills.citation_audit.implementation import ClaimSplitter


ROOT = Path(__file__).parents[1]


class StaticTransport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def complete(self, **request):
        self.calls.append(request)
        return self.response


def evidence() -> EvidenceRecord:
    payload = json.loads((ROOT / "a5/fixtures/evidence.json").read_text(encoding="utf-8"))[0]
    return EvidenceRecord.model_validate(payload)


def plan() -> AgentPlan:
    return AgentPlan(
        question_type="general_evidence",
        selected_skill="evidence_research@0.2.0",
        search_plan=SearchPlan(
            queries=["synthetic"],
            preferred_sources=["guideline"],
            expected_evidence_types=["guideline"],
            max_tool_calls=1,
        ),
        policy_version="test",
    )


def generated_payload(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "claim_id": "C-PROD",
        "text": "Artificial outcome A is improved",
        "criticality": "critical",
        "evidence_ids": ["E1"],
        "evidence_span_ids": ["S-E1"],
        "uncertainty": "LOW",
    }
    row.update(changes)
    return {"claims": [row]}


def generator(transport: StaticTransport) -> OpenAICompatibleClaimGenerator:
    return OpenAICompatibleClaimGenerator(
        transport=transport,
        model="injected-test-model",
        prompt_path=ROOT / "prompts/claim_generation_v0.4.0.md",
    )


def test_structured_generator_uses_schema_and_whitelists() -> None:
    transport = StaticTransport(generated_payload())
    claims = generator(transport).generate(Question(text="synthetic"), [evidence()], plan(), "RUN-X")
    assert claims[0].run_id == "RUN-X"
    assert claims[0].evidence_ids == ["E1"]
    assert transport.calls[0]["response_schema"]["title"] == "ClaimGenerationOutput"


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"evidence_ids": ["E999"]}, "generation_whitelist_violation"),
        # Adversarial-only strings: these are generator outputs under test, not evidence fixtures.
        ({"text": "See PMID:12345"}, "generated_external_reference"),
        ({"text": "See https://pubmed.ncbi.nlm.nih.gov/31452104/"}, "generated_external_reference"),
    ],
)
def test_structured_generator_fails_closed(changes: dict[str, object], reason: str) -> None:
    with pytest.raises(ClaimGenerationError, match=reason):
        generator(StaticTransport(generated_payload(**changes))).generate(
            Question(text="synthetic"), [evidence()], plan(), "RUN-X"
        )


def test_independent_semantic_unknown_never_becomes_supported() -> None:
    semantic = OpenAICompatibleSemanticEvaluator(
        transport=StaticTransport(
            {"status": "UNKNOWN", "entailment_score": None, "used_span_ids": [], "reason": "missing"}
        ),
        model="independent-test-model",
        prompt_path=ROOT / "prompts/semantic_verification_v0.4.0.md",
    )
    claim = generator(StaticTransport(generated_payload())).generate(
        Question(text="synthetic"), [evidence()], plan(), "RUN-X"
    )[0]
    composite = CompositeTextualSupportEvaluator(ExactSpanTextualSupportEvaluator(), semantic)
    assert composite.evaluate(claim, [evidence()]).status is VerificationStatus.INSUFFICIENT


class CountingSplitter:
    def __init__(self) -> None:
        self.calls = 0
        self.delegate = ClaimSplitter()

    def split(self, claims):
        self.calls += 1
        return self.delegate.split(claims)


def test_gate3_gate4_are_explicit_ordered_and_split_once() -> None:
    workflow = build_demo_workflow()
    splitter = CountingSplitter()
    workflow._audit_skill._splitter = splitter
    run = workflow.answer(
        Question(
            text="Artificial workflow question.",
            metadata={"mock_safety_decision": "ALLOW", "fixture_batches": [["E1"], ["E2"]]},
        )
    )
    assert run.decision is Decision.PASS
    assert run.atomic_claim_plan is not None
    assert run.generation_constraints is not None
    assert splitter.calls == 1
    states = [event.state for event in run.trace]
    assert states.index(WorkflowState.GATE3) < states.index(WorkflowState.GATE4)
    assert states.index(WorkflowState.GATE4) < states.index(WorkflowState.CLAIM_SPLITTER)
    assert states.index(WorkflowState.CLAIM_SPLITTER) < states.index(WorkflowState.GATE5)


def test_gate2_never_reuses_quality_as_query_local_ranking_score() -> None:
    record = evidence()
    gate = EvidenceSufficiencyGate(load_runtime_config().gates.gate2)
    missing = gate.evaluate(
        [record], freshness_required=False, budget_remaining=0, as_of_date=date(2026, 8, 12)
    )
    assert missing.metrics.top_score == pytest.approx(0.95)
    assert missing.metrics.top_ranking_score is None
    ranked_record = record.model_copy(
        update={"source_metadata": {**record.source_metadata, "ranking_score": 0.67}}
    )
    explicit = gate.evaluate(
        [ranked_record], freshness_required=False, budget_remaining=0, as_of_date=date(2026, 8, 12)
    )
    assert explicit.metrics.top_score == pytest.approx(0.95)
    assert explicit.metrics.top_ranking_score == pytest.approx(0.67)


def test_versioned_agent_run_schema_and_all_replays_validate() -> None:
    root = ROOT / "contracts/a5/v0.4.0"
    exported = json.loads((root / "schemas/AgentRun.schema.json").read_text(encoding="utf-8"))
    assert exported == AgentRun.model_json_schema()
    assert json.loads((root / "schemas/AgentRunView.schema.json").read_text(encoding="utf-8")) == AgentRunView.model_json_schema()
    for case, decision in {
        "PASS": Decision.PASS,
        "WARN": Decision.WARN,
        "REFUSE": Decision.REFUSE,
        "ERROR": Decision.REFUSE,
    }.items():
        assert answer_text("ignored replay text", mode="replay", replay_case=case).decision is decision


def test_ui_projection_hides_mock_urls_and_refused_claim_text() -> None:
    passed = answer_text("ignored", mode="replay", replay_case="PASS")
    # Corrupt/adversarial projection input: even a verified public URL must be
    # hidden when upstream marks the record as mock.
    passed.retrieved_evidence[0].source_metadata["url"] = "https://pubmed.ncbi.nlm.nih.gov/31452104/"
    pass_view = to_ui_view(passed)
    assert pass_view.evidence_cards
    assert all(card.mock and card.url is None for card in pass_view.evidence_cards)

    refused = answer_text("ignored", mode="replay", replay_case="REFUSE")
    refused_view = to_ui_view(refused)
    serialized = refused_view.model_dump_json()
    assert refused_view.included_claim_ids == []
    assert refused_view.evidence_cards == []
    assert all(claim.text not in serialized for claim in refused.claims)


def test_ui_projection_sanitizes_internal_error_and_live_requires_dependencies() -> None:
    view = to_ui_view(answer_text("ignored", mode="replay", replay_case="ERROR"))
    assert view.error_code is not None
    assert "fixture upstream unavailable" not in (view.error_message or "")
    with pytest.raises(ValueError, match="injected BackendDependencies"):
        answer_text("live question", mode="live")
