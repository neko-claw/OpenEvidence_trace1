from a5.adapters.default_safety_policy import DefaultSafetyPolicy
from a5.adapters.mock_claim_generator import MockClaimGenerator
from a5.adapters.mock_evidence_retriever import MockEvidenceRetriever
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.agent.workflow import A5Workflow
from a5.domain.enums import Decision, VerificationStatus, WorkflowState
from a5.domain.models import Question, RetrievalResult
from a5.observability.trace import render_trace
from a5.ports.evidence_retriever import EvidenceRetriever


def workflow(retriever=None) -> A5Workflow:
    return A5Workflow(
        retriever=retriever or MockEvidenceRetriever(),
        claim_generator=MockClaimGenerator(),
        claim_verifier=RuleBasedClaimVerifier(),
        safety_policy=DefaultSafetyPolicy(),
    )


def question(ids: list[str], **metadata) -> Question:
    return Question(
        text="Artificial treatment workflow question.",
        metadata={"fixture_evidence_ids": ids, **metadata},
    )


def test_pass_when_all_critical_claims_are_supported() -> None:
    run = workflow().answer(question(["E1", "E2"]))
    assert run.decision is Decision.PASS
    assert run.final_answer is not None
    assert run.final_answer.included_claim_ids == ["C1", "C2"]


def test_warn_when_critical_supported_and_important_insufficient() -> None:
    run = workflow().answer(question(["E1", "E3"]))
    assert run.decision is Decision.WARN
    assert run.final_answer is not None
    assert run.final_answer.included_claim_ids == ["C1"]
    assert "C3" not in run.final_answer.included_claim_ids


def test_refuse_when_no_valid_evidence() -> None:
    run = workflow().answer(question([]))
    assert run.decision is Decision.REFUSE
    assert run.final_answer is not None
    assert run.final_answer.included_claim_ids == []


def test_illegal_evidence_id_can_never_pass() -> None:
    run = workflow().answer(
        question(["E1"], inject_illegal_evidence_id="E999")
    )
    assert run.decision is Decision.REFUSE
    assert run.verification_results[0].illegal_evidence_ids == ["E999"]


def test_unsupported_critical_claim_refuses() -> None:
    run = workflow().answer(question(["E4"]))
    assert run.decision is Decision.REFUSE
    assert run.verification_results[0].status is VerificationStatus.CONTRADICTED


class AlternateEmptyRetriever:
    def retrieve(self, question, plan):
        return RetrievalResult(evidence=[], tool_name="alternate_empty")


def test_workflow_accepts_replaceable_non_mock_adapter() -> None:
    adapter = AlternateEmptyRetriever()
    assert isinstance(adapter, EvidenceRetriever)
    run = workflow(adapter).answer("Any question")
    assert run.decision is Decision.REFUSE
    retrieve_event = next(e for e in run.trace if e.state is WorkflowState.RETRIEVE)
    assert retrieve_event.tool == "alternate_empty"


def test_temporary_safety_policy_refuses_explicit_rejection() -> None:
    run = workflow().answer(question(["E1"], safety_allowed=False))
    assert run.decision is Decision.REFUSE
    assert [event.state for event in run.trace] == [
        WorkflowState.CLASSIFY,
        WorkflowState.FINALIZE,
        WorkflowState.END,
    ]


def test_trace_contains_full_happy_path_and_serializes() -> None:
    run = workflow().answer(question(["E1", "E2"]))
    assert [event.state for event in run.trace] == list(WorkflowState)
    assert run.trace[-1].final_decision is Decision.PASS
    assert "mock_search" in run.model_dump_json()
    rendered = render_trace(run)
    assert "type=treatment_evidence" in rendered
    assert "sources=guideline,systematic_review,primary_study" in rendered
    assert "input=query_count=1,max_tool_calls=3" in rendered
