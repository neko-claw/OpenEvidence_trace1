from a5.adapters.default_safety_policy import DefaultSafetyPolicy
from a5.adapters.mock_claim_generator import MockClaimGenerator
from a5.adapters.mock_evidence_retriever import MockEvidenceRetriever
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.agent.workflow import A5Workflow
from a5.domain.enums import ClaimCriticality, Decision, VerificationStatus
from a5.domain.models import Claim, Question


def build_workflow(*, retriever=None, generator=None) -> A5Workflow:
    return A5Workflow(
        retriever=retriever or MockEvidenceRetriever(),
        claim_generator=generator or MockClaimGenerator(),
        claim_verifier=RuleBasedClaimVerifier(),
        safety_policy=DefaultSafetyPolicy(),
    )


def fixture_question(ids: list[str]) -> Question:
    return Question(text="Artificial fixture", metadata={"fixture_evidence_ids": ids})


def test_explicit_conflict_refuses() -> None:
    run = build_workflow().answer(fixture_question(["E5"]))
    assert run.decision is Decision.REFUSE
    assert run.verification_results[0].status is VerificationStatus.CONTRADICTED
    assert "conflict" in run.verification_results[0].reason.casefold()


class EmptyClaimGenerator:
    def generate(self, question, evidence, plan):
        return []


def test_evidence_without_verifiable_claims_refuses() -> None:
    run = build_workflow(generator=EmptyClaimGenerator()).answer(fixture_question(["E1"]))
    assert run.decision is Decision.REFUSE


class CriticalInsufficientGenerator:
    def generate(self, question, evidence, plan):
        return [
            Claim(
                claim_id="C-NO-MARKER",
                text="Artificial critical claim without a support marker.",
                criticality=ClaimCriticality.CRITICAL,
                evidence_ids=["E3"],
                uncertainty=0.8,
            )
        ]


def test_critical_insufficient_claim_refuses() -> None:
    run = build_workflow(generator=CriticalInsufficientGenerator()).answer(
        fixture_question(["E3"])
    )
    assert run.decision is Decision.REFUSE
    assert run.verification_results[0].status is VerificationStatus.INSUFFICIENT


class ExplodingRetriever:
    def retrieve(self, question, plan):
        raise RuntimeError("synthetic retrieval failure")


def test_tool_error_fails_closed_and_is_observable() -> None:
    run = build_workflow(retriever=ExplodingRetriever()).answer("Artificial fixture")
    assert run.decision is Decision.REFUSE
    assert run.error == "RuntimeError: synthetic retrieval failure"
    assert any(event.error for event in run.trace)
    assert run.final_answer is not None


def test_final_citations_are_subset_of_retrieved_whitelist() -> None:
    run = build_workflow().answer(fixture_question(["E1", "E2"]))
    retrieved = {record.id for record in run.retrieved_evidence}
    assert set(run.final_answer.cited_evidence_ids) <= retrieved
