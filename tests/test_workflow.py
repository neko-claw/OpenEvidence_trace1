from a5.adapters.default_safety_policy import DefaultFailClosedSafetyPolicy, FixtureSafetyPolicy
from a5.adapters.mock_claim_generator import MockClaimGenerator
from a5.adapters.mock_evidence_retriever import MockEvidenceRetriever
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.agent.budget import ToolBudgetExceeded, ToolBudgetManager
from a5.agent.router import SkillRouter
from a5.agent.workflow import A5Workflow
from a5.domain.enums import (
    ClaimCriticality,
    Decision,
    SafetyDecision,
    UncertaintyLevel,
    VerificationStatus,
    WorkflowState,
)
from a5.domain.models import Claim, Question, RetrievalResult
from a5.observability.trace import render_trace
from a5.ports.evidence_retriever import EvidenceRetriever
from a5.runtime_config import load_runtime_config


def workflow(*, retriever=None, generator=None, safety=None) -> A5Workflow:
    config = load_runtime_config()
    return A5Workflow(
        retriever=retriever or MockEvidenceRetriever(),
        claim_generator=generator or MockClaimGenerator(),
        claim_verifier=RuleBasedClaimVerifier(config.gates.gate5),
        safety_policy=safety or FixtureSafetyPolicy(),
        runtime_config=config,
    )


def question(batches: list[list[str]], **metadata) -> Question:
    return Question(
        text="Artificial treatment workflow question.",
        metadata={"fixture_batches": batches, "mock_safety_decision": "ALLOW", **metadata},
    )


def test_pass_warn_and_refuse_release_paths() -> None:
    passed = workflow().answer(question([["E1"], ["E2"]]))
    warned = workflow().answer(question([["E1"], ["E3"]]))
    refused = workflow().answer(question([[], [], []]))
    assert passed.decision is Decision.PASS
    assert passed.final_answer.included_claim_ids == ["C1", "C2"]
    assert warned.decision is Decision.WARN
    assert warned.final_answer.included_claim_ids == ["C1"]
    assert refused.decision is Decision.REFUSE
    assert any("budget_exhausted" in item for item in refused.final_answer.limitations)


def test_tool_budget_manager_prohibits_n_plus_one_call() -> None:
    budget = ToolBudgetManager(2)
    budget.consume()
    snapshot = budget.consume()
    assert snapshot.budget_exhausted is True
    try:
        budget.consume()
    except ToolBudgetExceeded:
        pass
    else:  # pragma: no cover
        raise AssertionError("N+1 tool call must be prohibited")


def test_workflow_retries_until_sufficient_then_stops_early() -> None:
    retriever = MockEvidenceRetriever()
    run = workflow(retriever=retriever).answer(question([["E1"], ["E2"], ["E3"]]))
    calls = [event for event in run.trace if event.state is WorkflowState.RETRIEVE]
    assert run.decision is Decision.PASS
    assert retriever.call_count == 2
    assert [event.tool_call_index for event in calls] == [1, 2]
    assert calls[-1].tool_budget_remaining == 1


def test_workflow_stops_after_first_sufficient_batch() -> None:
    retriever = MockEvidenceRetriever()
    run = workflow(retriever=retriever).answer(question([["E1", "E2"], ["E3"]]))
    assert run.decision is Decision.PASS
    assert retriever.call_count == 1


def test_skill_router_selects_research_and_citation_audit_from_config() -> None:
    config = load_runtime_config()
    router = SkillRouter(config)
    assert router.route(WorkflowState.CLASSIFY, "treatment_evidence") == (
        f"evidence_research@{config.skills.evidence_research.version}"
    )
    assert router.route(WorkflowState.GATE5, "treatment_evidence") == (
        f"citation_audit@{config.skills.citation_audit.version}"
    )


def test_gate0_unknown_refuses_before_retrieval_or_generation() -> None:
    retriever = MockEvidenceRetriever()
    run = workflow(retriever=retriever, safety=DefaultFailClosedSafetyPolicy()).answer(
        question([["E1", "E2"]])
    )
    assert run.safety_assessment.decision is SafetyDecision.UNKNOWN
    assert run.decision is Decision.REFUSE
    assert retriever.call_count == 0
    assert not any(event.state is WorkflowState.GENERATE_CLAIMS for event in run.trace)


def test_gate0_deny_refuses_before_retrieval() -> None:
    retriever = MockEvidenceRetriever()
    run = workflow(retriever=retriever).answer(
        Question(text="fixture", metadata={"mock_safety_decision": "DENY"})
    )
    assert run.decision is Decision.REFUSE
    assert retriever.call_count == 0


def test_illegal_evidence_id_and_unsupported_critical_claim_refuse() -> None:
    illegal = workflow().answer(
        question([["E1", "E2"]], inject_illegal_evidence_id="E999")
    )
    contradicted = workflow().answer(question([["E1", "E4"]]))
    assert illegal.decision is Decision.REFUSE
    assert illegal.verification_results[0].illegal_evidence_ids == ["E999"]
    assert contradicted.decision is Decision.REFUSE
    assert any(
        result.status in {VerificationStatus.CONTRADICTED, VerificationStatus.INSUFFICIENT}
        for result in contradicted.verification_results
        if result.claim_id == "C4"
    )


class HighUncertaintyGenerator:
    def generate(self, question, evidence, plan, run_id):
        del question, evidence, plan
        return [
            Claim(
                claim_id="C-HIGH",
                run_id=run_id,
                text="Artificial outcome A is improved",
                criticality=ClaimCriticality.CRITICAL,
                evidence_ids=["E1"],
                evidence_span_ids=["S-E1"],
                uncertainty=UncertaintyLevel.HIGH,
                population="synthetic population",
                intervention="synthetic intervention",
                comparator="synthetic comparator",
                outcome="synthetic outcome A",
            )
        ]


def test_high_uncertainty_critical_claim_cannot_silently_pass() -> None:
    run = workflow(generator=HighUncertaintyGenerator()).answer(question([["E1", "E2"]]))
    assert run.verification_results[0].status is VerificationStatus.SUPPORTED
    assert run.decision is Decision.REFUSE
    assert "high_uncertainty" in run.final_answer.limitations[0]


class AlternateEmptyRetriever:
    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, question, plan, request):
        del question, plan, request
        self.calls += 1
        return RetrievalResult(evidence=[], tool_name="alternate_empty")


def test_mock_adapter_can_be_replaced_without_workflow_edits() -> None:
    adapter = AlternateEmptyRetriever()
    assert isinstance(adapter, EvidenceRetriever)
    run = workflow(retriever=adapter).answer(question([[], [], []]))
    assert run.decision is Decision.REFUSE
    assert adapter.calls == load_runtime_config().agent.max_tool_calls
    assert any(event.tool == "alternate_empty" for event in run.trace)


class ExplodingRetriever:
    def retrieve(self, question, plan, request):
        raise RuntimeError("synthetic retrieval failure")


def test_tool_error_fails_closed_and_is_observable() -> None:
    run = workflow(retriever=ExplodingRetriever()).answer(question([["E1"]]))
    assert run.decision is Decision.REFUSE
    assert run.error == "RuntimeError: synthetic retrieval failure"
    assert any(event.error for event in run.trace)


def test_trace_and_run_capture_versions_config_and_full_happy_path() -> None:
    config = load_runtime_config()
    run = workflow().answer(question([["E1"], ["E2"]]))
    states = [event.state for event in run.trace]
    for required in (
        WorkflowState.GATE0,
        WorkflowState.SELECT_SKILL,
        WorkflowState.RETRIEVE,
        WorkflowState.GATE2,
        WorkflowState.SUMMARIZE_EVIDENCE,
        WorkflowState.GENERATE_CLAIMS,
        WorkflowState.CLAIM_SPLITTER,
        WorkflowState.GATE5,
        WorkflowState.GATE6,
    ):
        assert required in states
    assert run.agent_version == config.agent.agent_version
    assert run.skill_versions["citation_audit"] == config.skills.citation_audit.version
    assert run.prompt_versions == config.skills.prompt_versions
    assert run.runtime_config_snapshot.gates["threshold_status"].startswith("development_default")
    assert "Gate2@" in render_trace(run)
    assert "mock_search" in run.model_dump_json()
