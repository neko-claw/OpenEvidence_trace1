from __future__ import annotations

from a5.domain.enums import WorkflowState
from a5.domain.models import AgentRun


class InvalidStateTransition(RuntimeError):
    pass


ALLOWED_TRANSITIONS: set[tuple[WorkflowState, WorkflowState]] = {
    (WorkflowState.START, WorkflowState.GATE0),
    (WorkflowState.GATE0, WorkflowState.CLASSIFY),
    (WorkflowState.GATE0, WorkflowState.GATE6),
    (WorkflowState.CLASSIFY, WorkflowState.SELECT_SKILL),
    (WorkflowState.SELECT_SKILL, WorkflowState.PLAN),
    (WorkflowState.PLAN, WorkflowState.RETRIEVE),
    (WorkflowState.RETRIEVE, WorkflowState.GATE2),
    (WorkflowState.GATE2, WorkflowState.RETRIEVE),
    (WorkflowState.GATE2, WorkflowState.SUMMARIZE_EVIDENCE),
    (WorkflowState.GATE2, WorkflowState.GATE6),
    (WorkflowState.SUMMARIZE_EVIDENCE, WorkflowState.GENERATE_CLAIMS),
    (WorkflowState.GENERATE_CLAIMS, WorkflowState.CLAIM_SPLITTER),
    (WorkflowState.CLAIM_SPLITTER, WorkflowState.AUDIT_CITATIONS),
    (WorkflowState.AUDIT_CITATIONS, WorkflowState.GATE5),
    (WorkflowState.GATE5, WorkflowState.GATE6),
    (WorkflowState.GATE6, WorkflowState.FINALIZE),
    (WorkflowState.FINALIZE, WorkflowState.END),
}


class AgentStateMachine:
    def __init__(self, run: AgentRun) -> None:
        self.run = run

    @property
    def state(self) -> WorkflowState:
        return self.run.state

    def transition(self, target: WorkflowState, *, fail_closed: bool = False) -> None:
        source = self.state
        if source is WorkflowState.END:
            raise InvalidStateTransition("END is terminal")
        allowed = (source, target) in ALLOWED_TRANSITIONS
        fail_closed_shortcut = fail_closed and target is WorkflowState.GATE6
        if not (allowed or fail_closed_shortcut):
            raise InvalidStateTransition(f"invalid transition: {source} -> {target}")
        self.run.state = target
