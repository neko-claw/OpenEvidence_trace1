from __future__ import annotations

from datetime import date
from time import perf_counter

from a5.agent.budget import ToolBudgetManager
from a5.agent.router import SkillRouter
from a5.agent.state import AgentStateMachine
from a5.domain.enums import (
    Decision,
    EvidenceIntegrityStatus,
    EventType,
    RecommendedAction,
    SafetyDecision,
    SufficiencyStatus,
    WorkflowState,
)
from a5.domain.models import (
    AgentRun,
    CitationAuditReport,
    Question,
    RetrievalRequest,
    ToolTrace,
    VerificationContext,
    utc_now,
)
from a5.gates.evidence_sufficiency import EvidenceSufficiencyGate
from a5.gates.evidence_integrity import EvidenceIntegrityGate
from a5.gates.release import ReleaseGate
from a5.generation.finalizer import Finalizer
from a5.ports.claim_generator import ClaimGenerator
from a5.ports.claim_verifier import ClaimVerifier
from a5.ports.evidence_retriever import EvidenceRetriever
from a5.ports.evidence_integrity import EvidenceIntegrityEvaluator
from a5.ports.safety_policy import SafetyPolicy
from a5.runtime_config import RuntimeConfig, load_runtime_config
from a5.skills.citation_audit import CitationAuditSkill
from a5.skills.evidence_research import EvidenceResearchSkill


class A5Workflow:
    """Restricted single-agent finite-state workflow with fail-closed gates."""

    def __init__(
        self,
        *,
        retriever: EvidenceRetriever,
        claim_generator: ClaimGenerator,
        claim_verifier: ClaimVerifier,
        safety_policy: SafetyPolicy,
        runtime_config: RuntimeConfig | None = None,
        evidence_integrity: EvidenceIntegrityEvaluator | None = None,
        research_skill: EvidenceResearchSkill | None = None,
        finalizer: Finalizer | None = None,
    ) -> None:
        self._config = runtime_config or load_runtime_config()
        self._retriever: EvidenceRetriever = retriever
        self._claim_generator: ClaimGenerator = claim_generator
        self._safety_policy: SafetyPolicy = safety_policy
        self._research_skill = research_skill or EvidenceResearchSkill(self._config)
        self._audit_skill = CitationAuditSkill(claim_verifier, self._config)
        self._router = SkillRouter(self._config)
        self._gate1: EvidenceIntegrityEvaluator = evidence_integrity or EvidenceIntegrityGate(
            self._config.gates.gate1
        )
        self._gate2 = EvidenceSufficiencyGate(self._config.gates.gate2)
        self._gate6 = ReleaseGate(self._config.gates.gate6)
        self._finalizer = finalizer or Finalizer()

    def answer(self, question: Question | str) -> AgentRun:
        normalized = Question(text=question) if isinstance(question, str) else question
        if "as_of_date" not in normalized.metadata:
            normalized = normalized.model_copy(
                update={"metadata": {**normalized.metadata, "as_of_date": utc_now().date().isoformat()}}
            )
        run = AgentRun(
            question=normalized,
            agent_version=self._config.agent.agent_version,
            skill_versions={
                "evidence_research": self._config.skills.evidence_research.version,
                "citation_audit": self._config.skills.citation_audit.version,
            },
            prompt_versions=dict(self._config.skills.prompt_versions),
            gate_config_version=self._config.gates.config_version,
            runtime_config_snapshot=self._config.snapshot(),
        )
        machine = AgentStateMachine(run)
        audit: CitationAuditReport | None = None
        refusal_reason: str | None = None
        as_of_date = self._as_of_date(normalized)
        self._trace(run, WorkflowState.START, EventType.STATE, perf_counter())
        try:
            machine.transition(WorkflowState.GATE0)
            started = perf_counter()
            run.safety_assessment = self._safety_policy.assess(run.question)
            self._trace(
                run,
                WorkflowState.GATE0,
                EventType.GATE,
                started,
                gate=f"Gate0@{self._config.gates.gate0_version}",
                decision=run.safety_assessment.decision.value,
                details={"reason": run.safety_assessment.reason, "policy": run.safety_assessment.policy_version},
            )
            if run.safety_assessment.decision is not SafetyDecision.ALLOW:
                machine.transition(WorkflowState.GATE6)
                run.decision, reasons = self._gate6.decide(
                    safety=run.safety_assessment,
                    integrity=None,
                    sufficiency=None,
                    claims=[],
                    results=[],
                )
                refusal_reason = "; ".join(reasons)
                self._trace_gate6(run, reasons)
                self._finalize(run, machine, None, refusal_reason)
                return self._finish(run)

            machine.transition(WorkflowState.CLASSIFY)
            started = perf_counter()
            question_type = self._research_skill.classify(run.question)
            self._trace(
                run,
                WorkflowState.CLASSIFY,
                EventType.STATE,
                started,
                details={"question_type": question_type},
            )

            machine.transition(WorkflowState.SELECT_SKILL)
            started = perf_counter()
            research_identifier = self._router.route(WorkflowState.CLASSIFY, question_type)
            run.selected_skill = research_identifier
            run.selected_skills.append(research_identifier)
            self._trace(
                run,
                WorkflowState.SELECT_SKILL,
                EventType.SKILL,
                started,
                skill=research_identifier,
                details={"route_reason": f"question_type={question_type}; stage=retrieval"},
            )

            machine.transition(WorkflowState.PLAN)
            started = perf_counter()
            run.agent_plan = self._research_skill.plan(run.question)
            self._trace(
                run,
                WorkflowState.PLAN,
                EventType.SKILL,
                started,
                skill=research_identifier,
                input_summary={"question_type": question_type},
                details={"agent_plan": run.agent_plan.model_dump(mode="json")},
            )

            budget = ToolBudgetManager(run.agent_plan.search_plan.max_tool_calls)
            machine.transition(WorkflowState.RETRIEVE)
            while True:
                sources = run.agent_plan.search_plan.preferred_sources
                source = sources[budget.used_tool_calls % len(sources)]
                budget_snapshot = budget.consume()
                request = RetrievalRequest(
                    source_type=source,
                    tool_call_index=budget_snapshot.used_tool_calls,
                )
                started = perf_counter()
                result = self._retriever.retrieve(run.question, run.agent_plan.search_plan, request)
                by_id = {record.id: record for record in run.retrieved_evidence}
                for record in result.evidence:
                    by_id[record.id] = record
                run.retrieved_evidence = list(by_id.values())
                self._trace(
                    run,
                    WorkflowState.RETRIEVE,
                    EventType.TOOL,
                    started,
                    skill=research_identifier,
                    tool=result.tool_name,
                    tool_call_index=request.tool_call_index,
                    tool_budget_remaining=budget_snapshot.remaining_tool_calls,
                    input_summary={"source_type": source, "query_count": len(run.agent_plan.search_plan.queries)},
                    output_count=len(result.evidence),
                    evidence_ids=[record.id for record in result.evidence],
                    details={"diagnostics": result.diagnostics},
                )
                machine.transition(WorkflowState.GATE1)
                started = perf_counter()
                run.evidence_integrity = self._gate1.evaluate(run.retrieved_evidence)
                eligible_ids = set(run.evidence_integrity.eligible_evidence_ids)
                self._trace(
                    run,
                    WorkflowState.GATE1,
                    EventType.GATE,
                    started,
                    gate=f"Gate1@{self._config.gates.gate1_version}",
                    tool_budget_remaining=budget.remaining_tool_calls,
                    evidence_ids=[record.id for record in run.retrieved_evidence],
                    decision=run.evidence_integrity.status.value,
                    details=run.evidence_integrity.model_dump(mode="json"),
                )
                if run.evidence_integrity.status is EvidenceIntegrityStatus.REJECTED:
                    machine.transition(WorkflowState.GATE6)
                    run.decision, reasons = self._gate6.decide(
                        safety=run.safety_assessment,
                        integrity=run.evidence_integrity,
                        sufficiency=None,
                        claims=[],
                        results=[],
                    )
                    refusal_reason = "; ".join(reasons)
                    self._trace_gate6(run, reasons)
                    self._finalize(run, machine, None, refusal_reason)
                    return self._finish(run)
                run.retrieved_evidence = [
                    record for record in run.retrieved_evidence if record.id in eligible_ids
                ]
                machine.transition(WorkflowState.GATE2)
                started = perf_counter()
                run.evidence_sufficiency = self._gate2.evaluate(
                    run.retrieved_evidence,
                    freshness_required=run.agent_plan.search_plan.freshness_required,
                    budget_remaining=budget.remaining_tool_calls,
                    as_of_date=as_of_date,
                )
                self._trace(
                    run,
                    WorkflowState.GATE2,
                    EventType.GATE,
                    started,
                    gate=f"Gate2@{self._config.gates.gate2_version}",
                    tool_budget_remaining=budget.remaining_tool_calls,
                    evidence_ids=[record.id for record in run.retrieved_evidence],
                    decision=run.evidence_sufficiency.status.value,
                    details=run.evidence_sufficiency.model_dump(mode="json"),
                )
                if run.evidence_sufficiency.status is SufficiencyStatus.SUFFICIENT:
                    machine.transition(WorkflowState.SUMMARIZE_EVIDENCE)
                    break
                if run.evidence_sufficiency.recommended_action is RecommendedAction.RETRY:
                    machine.transition(WorkflowState.RETRIEVE)
                    continue
                machine.transition(WorkflowState.GATE6)
                run.decision, reasons = self._gate6.decide(
                    safety=run.safety_assessment,
                    integrity=run.evidence_integrity,
                    sufficiency=run.evidence_sufficiency,
                    claims=[],
                    results=[],
                )
                refusal_reason = "; ".join(reasons)
                self._trace_gate6(run, reasons)
                self._finalize(run, machine, None, refusal_reason)
                return self._finish(run)

            started = perf_counter()
            run.evidence_summary = self._research_skill.summarize(
                run.retrieved_evidence,
                freshness_required=run.agent_plan.search_plan.freshness_required,
                as_of_date=as_of_date,
            )
            run.agent_plan.evidence_summary = run.evidence_summary
            self._trace(
                run,
                WorkflowState.SUMMARIZE_EVIDENCE,
                EventType.SKILL,
                started,
                skill=research_identifier,
                evidence_ids=run.evidence_summary.evidence_ids,
                output_count=run.evidence_summary.evidence_count,
                details=run.evidence_summary.model_dump(mode="json"),
            )

            machine.transition(WorkflowState.GENERATE_CLAIMS)
            started = perf_counter()
            candidates = self._claim_generator.generate(
                run.question, run.retrieved_evidence, run.agent_plan, run.run_id
            )
            self._trace(
                run,
                WorkflowState.GENERATE_CLAIMS,
                EventType.GENERATION,
                started,
                skill=f"claim_generation@{run.prompt_versions['claim_generation']}",
                claim_ids=[claim.claim_id for claim in candidates],
                output_count=len(candidates),
            )

            machine.transition(WorkflowState.CLAIM_SPLITTER)
            started = perf_counter()
            audit_identifier = self._router.route(WorkflowState.CLAIM_SPLITTER, question_type)
            run.selected_skill = audit_identifier
            run.selected_skills.append(audit_identifier)
            run.claims = self._audit_skill.split_claims(candidates)
            self._trace(
                run,
                WorkflowState.CLAIM_SPLITTER,
                EventType.SKILL,
                started,
                skill=audit_identifier,
                claim_ids=[claim.claim_id for claim in run.claims],
                output_count=len(run.claims),
                details={"route_reason": "stage=claim_verification"},
            )

            machine.transition(WorkflowState.AUDIT_CITATIONS)
            started = perf_counter()
            audit = self._audit_skill.audit(
                run.claims,
                run.retrieved_evidence,
                VerificationContext(
                    freshness_required=run.agent_plan.search_plan.freshness_required,
                    run_date=as_of_date,
                ),
            )
            self._trace(
                run,
                WorkflowState.AUDIT_CITATIONS,
                EventType.SKILL,
                started,
                skill=audit_identifier,
                claim_ids=[claim.claim_id for claim in run.claims],
                decision=audit.decision.value,
                details={"approved": audit.approved_claim_ids, "rejected": audit.rejected_claim_ids},
            )

            machine.transition(WorkflowState.GATE5)
            started = perf_counter()
            run.verification_results = audit.verification_results
            result_by_id = {item.claim_id: item for item in run.verification_results}
            run.claims = [
                claim.model_copy(
                    update={
                        "entailment_score": result_by_id[claim.claim_id].entailment_score,
                        "population_match": result_by_id[claim.claim_id].population_match,
                        "intervention_match": result_by_id[claim.claim_id].intervention_match,
                        "comparator_match": result_by_id[claim.claim_id].comparator_match,
                        "outcome_match": result_by_id[claim.claim_id].outcome_match,
                        "time_match": result_by_id[claim.claim_id].time_match,
                        "conflict_ids": result_by_id[claim.claim_id].conflict_ids,
                        "verification_method": result_by_id[claim.claim_id].verification_method,
                        "decision": result_by_id[claim.claim_id].status,
                    }
                )
                for claim in run.claims
                if claim.claim_id in result_by_id
            ]
            self._trace(
                run,
                WorkflowState.GATE5,
                EventType.GATE,
                started,
                gate=f"Gate5@{self._config.gates.gate5_version}",
                skill=audit_identifier,
                claim_ids=[claim.claim_id for claim in run.claims],
                details={
                    "results": [result.model_dump(mode="json") for result in run.verification_results]
                },
            )

            machine.transition(WorkflowState.GATE6)
            run.decision, release_reasons = self._gate6.decide(
                safety=run.safety_assessment,
                integrity=run.evidence_integrity,
                sufficiency=run.evidence_sufficiency,
                claims=run.claims,
                results=run.verification_results,
            )
            audit = audit.model_copy(
                update={
                    "decision": run.decision,
                    "reasons": list(dict.fromkeys(audit.reasons + release_reasons)),
                }
            )
            refusal_reason = "; ".join(release_reasons) if run.decision is Decision.REFUSE else None
            self._trace_gate6(run, release_reasons)
            self._finalize(run, machine, audit, refusal_reason)
        except Exception as exc:
            self._handle_error(run, machine, exc)
        return self._finish(run)

    def _trace_gate6(self, run: AgentRun, reasons: list[str]) -> None:
        self._trace(
            run,
            WorkflowState.GATE6,
            EventType.DECISION,
            perf_counter(),
            gate=f"Gate6@{self._config.gates.gate6_version}",
            decision=(run.decision or Decision.REFUSE).value,
            details={"reasons": reasons},
        )

    def _finalize(
        self,
        run: AgentRun,
        machine: AgentStateMachine,
        audit: CitationAuditReport | None,
        refusal_reason: str | None,
    ) -> None:
        machine.transition(WorkflowState.FINALIZE)
        started = perf_counter()
        run.decision = run.decision or Decision.REFUSE
        run.final_answer = self._finalizer.finalize(run.decision, run.claims, audit, refusal_reason)
        self._trace(
            run,
            WorkflowState.FINALIZE,
            EventType.DECISION,
            started,
            decision=run.decision.value,
            claim_ids=run.final_answer.included_claim_ids,
            evidence_ids=run.final_answer.cited_evidence_ids,
            details={"limitations": run.final_answer.limitations},
        )
        machine.transition(WorkflowState.END)

    def _handle_error(self, run: AgentRun, machine: AgentStateMachine, exc: Exception) -> None:
        run.error = f"{type(exc).__name__}: {exc}"
        run.decision = Decision.REFUSE
        self._trace(run, machine.state, EventType.ERROR, perf_counter(), error=run.error)
        if machine.state not in {WorkflowState.GATE6, WorkflowState.FINALIZE, WorkflowState.END}:
            machine.transition(WorkflowState.GATE6, fail_closed=True)
            self._trace_gate6(run, ["workflow_error: failed closed"])
        if machine.state is WorkflowState.GATE6:
            self._finalize(run, machine, None, "Workflow error; failed closed.")

    def _finish(self, run: AgentRun) -> AgentRun:
        if run.finished_at is None:
            run.finished_at = utc_now()
            run.latency_ms = (run.finished_at - run.started_at).total_seconds() * 1000
            self._trace(
                run,
                WorkflowState.END,
                EventType.STATE,
                perf_counter(),
                decision=(run.decision or Decision.REFUSE).value,
                details={"run_latency_ms": run.latency_ms},
            )
        return run

    @staticmethod
    def _as_of_date(question: Question) -> date:
        raw = question.metadata.get("as_of_date")
        if isinstance(raw, date):
            return raw
        if isinstance(raw, str):
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
        return utc_now().date()

    @staticmethod
    def _trace(
        run: AgentRun,
        state: WorkflowState,
        event_type: EventType,
        started: float,
        **kwargs: object,
    ) -> None:
        run.trace.append(
            ToolTrace(
                run_id=run.run_id,
                state=state,
                event_type=event_type,
                latency_ms=max((perf_counter() - started) * 1000, 0.0),
                **kwargs,
            )
        )
