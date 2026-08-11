from __future__ import annotations

from time import perf_counter

from a5.agent.planner import AgentPlanner
from a5.agent.state import AgentStateMachine
from a5.domain.enums import Decision, SafetyStatus, WorkflowState
from a5.domain.models import (
    AgentRun,
    CitationAuditReport,
    Question,
    ToolTrace,
    utc_now,
)
from a5.generation.finalizer import Finalizer
from a5.ports.claim_generator import ClaimGenerator
from a5.ports.claim_verifier import ClaimVerifier
from a5.ports.evidence_retriever import EvidenceRetriever
from a5.ports.safety_policy import SafetyPolicy
from a5.skills.citation_audit import CitationAuditSkill
from a5.skills.evidence_research import EvidenceResearchSkill


class A5Workflow:
    """Single-agent, finite-state, fail-closed trustworthy generation workflow."""

    def __init__(
        self,
        *,
        retriever: EvidenceRetriever,
        claim_generator: ClaimGenerator,
        claim_verifier: ClaimVerifier,
        safety_policy: SafetyPolicy,
        research_skill: EvidenceResearchSkill | None = None,
        finalizer: Finalizer | None = None,
    ) -> None:
        self._retriever = retriever
        self._claim_generator = claim_generator
        self._safety_policy = safety_policy
        self._research_skill = research_skill or EvidenceResearchSkill()
        self._planner = AgentPlanner(self._research_skill)
        self._audit_skill = CitationAuditSkill(claim_verifier)
        self._finalizer = finalizer or Finalizer()

    def answer(self, question: Question | str) -> AgentRun:
        normalized_question = Question(text=question) if isinstance(question, str) else question
        run = AgentRun(question=normalized_question)
        machine = AgentStateMachine(run)
        audit: CitationAuditReport | None = None
        refusal_reason: str | None = None

        try:
            step_started = perf_counter()
            run.safety_assessment = self._safety_policy.assess(run.question)
            question_type = self._planner.classify(run.question)
            self._trace(
                run,
                WorkflowState.CLASSIFY,
                step_started,
                details={
                    "question_type": question_type,
                    "safety_status": run.safety_assessment.status.value,
                    "safety_policy": run.safety_assessment.policy_version,
                },
            )
            if run.safety_assessment.status is SafetyStatus.REFUSED:
                run.decision = Decision.REFUSE
                refusal_reason = run.safety_assessment.reason
                machine.transition(WorkflowState.FINALIZE, fail_closed=True)
            else:
                machine.transition(WorkflowState.PLAN)

            if machine.state is WorkflowState.PLAN:
                step_started = perf_counter()
                run.agent_plan = self._planner.create_plan(run.question)
                self._trace(
                    run,
                    WorkflowState.PLAN,
                    step_started,
                    agent_plan=run.agent_plan.model_dump(mode="json"),
                    details={"question_type": run.agent_plan.question_type},
                )
                machine.transition(WorkflowState.SELECT_SKILL)

                step_started = perf_counter()
                run.selected_skill = run.agent_plan.selected_skill
                self._trace(
                    run,
                    WorkflowState.SELECT_SKILL,
                    step_started,
                    selected_skill=run.selected_skill,
                )
                machine.transition(WorkflowState.RETRIEVE)

                step_started = perf_counter()
                retrieval = self._retriever.retrieve(run.question, run.agent_plan.search_plan)
                run.retrieved_evidence = retrieval.evidence
                self._trace(
                    run,
                    WorkflowState.RETRIEVE,
                    step_started,
                    selected_skill=run.selected_skill,
                    tool=retrieval.tool_name,
                    tool_input_summary={
                        "query_count": len(run.agent_plan.search_plan.queries),
                        "max_tool_calls": run.agent_plan.search_plan.max_tool_calls,
                    },
                    tool_output_count=len(retrieval.evidence),
                    retrieved_evidence_ids=[record.id for record in retrieval.evidence],
                    details={"diagnostics": retrieval.diagnostics},
                )
                machine.transition(WorkflowState.CHECK_EVIDENCE)

                step_started = perf_counter()
                evidence_ids = [record.id for record in run.retrieved_evidence]
                if not evidence_ids:
                    refusal_reason = "No valid evidence was retrieved."
                elif len(evidence_ids) != len(set(evidence_ids)):
                    refusal_reason = "Retrieved evidence IDs are not unique."
                self._trace(
                    run,
                    WorkflowState.CHECK_EVIDENCE,
                    step_started,
                    tool_output_count=len(evidence_ids),
                    retrieved_evidence_ids=evidence_ids,
                    details={"valid": refusal_reason is None},
                )
                if refusal_reason:
                    run.decision = Decision.REFUSE
                    machine.transition(WorkflowState.FINALIZE, fail_closed=True)
                else:
                    machine.transition(WorkflowState.GENERATE_CLAIMS)

            if machine.state is WorkflowState.GENERATE_CLAIMS:
                step_started = perf_counter()
                assert run.agent_plan is not None
                run.claims = self._claim_generator.generate(
                    run.question, run.retrieved_evidence, run.agent_plan
                )
                self._trace(
                    run,
                    WorkflowState.GENERATE_CLAIMS,
                    step_started,
                    selected_skill=run.selected_skill,
                    generated_claim_ids=[claim.claim_id for claim in run.claims],
                    tool_output_count=len(run.claims),
                )
                machine.transition(WorkflowState.VERIFY_CLAIMS)

                step_started = perf_counter()
                audit = self._audit_skill.audit(run.claims, run.retrieved_evidence)
                run.verification_results = audit.verification_results
                run.decision = audit.decision
                self._trace(
                    run,
                    WorkflowState.VERIFY_CLAIMS,
                    step_started,
                    selected_skill=self._audit_skill.identifier,
                    verification_result={
                        result.claim_id: result.status.value
                        for result in run.verification_results
                    },
                    final_decision=run.decision,
                    details={
                        "approved_claim_ids": audit.approved_claim_ids,
                        "rejected_claim_ids": audit.rejected_claim_ids,
                        "reasons": audit.reasons,
                    },
                )
                machine.transition(WorkflowState.FINALIZE)

            self._finalize(run, machine, audit, refusal_reason)
        except Exception as exc:  # fail closed at the orchestration boundary
            self._handle_error(run, machine, exc)

        run.finished_at = utc_now()
        run.latency_ms = (run.finished_at - run.started_at).total_seconds() * 1000
        self._trace(
            run,
            WorkflowState.END,
            perf_counter(),
            final_decision=run.decision,
            details={"run_latency_ms": run.latency_ms},
        )
        return run

    def _finalize(
        self,
        run: AgentRun,
        machine: AgentStateMachine,
        audit: CitationAuditReport | None,
        refusal_reason: str | None,
    ) -> None:
        step_started = perf_counter()
        run.decision = run.decision or Decision.REFUSE
        run.final_answer = self._finalizer.finalize(
            run.decision, run.claims, audit, refusal_reason
        )
        self._trace(
            run,
            WorkflowState.FINALIZE,
            step_started,
            final_decision=run.decision,
            generated_claim_ids=run.final_answer.included_claim_ids,
            details={"limitations": run.final_answer.limitations},
        )
        machine.transition(WorkflowState.END)

    def _handle_error(
        self,
        run: AgentRun,
        machine: AgentStateMachine,
        exc: Exception,
    ) -> None:
        run.error = f"{type(exc).__name__}: {exc}"
        run.decision = Decision.REFUSE
        self._trace(run, machine.state, perf_counter(), error=run.error)
        if machine.state not in (WorkflowState.FINALIZE, WorkflowState.END):
            machine.transition(WorkflowState.FINALIZE, fail_closed=True)
        if machine.state is WorkflowState.FINALIZE:
            run.final_answer = self._finalizer.finalize(
                Decision.REFUSE, run.claims, None, "Workflow error; failed closed."
            )
            self._trace(
                run,
                WorkflowState.FINALIZE,
                perf_counter(),
                final_decision=Decision.REFUSE,
                error=run.error,
            )
            machine.transition(WorkflowState.END)

    @staticmethod
    def _trace(
        run: AgentRun,
        state: WorkflowState,
        started: float,
        **kwargs: object,
    ) -> None:
        latency_ms = max((perf_counter() - started) * 1000, 0.0)
        run.trace.append(ToolTrace(state=state, latency_ms=latency_ms, **kwargs))
