from __future__ import annotations

from a5.domain.enums import WorkflowState
from a5.domain.models import AgentRun


class InvalidStateTransition(RuntimeError):
    pass


NORMAL_NEXT_STATE: dict[WorkflowState, WorkflowState] = {
    WorkflowState.CLASSIFY: WorkflowState.PLAN,
    WorkflowState.PLAN: WorkflowState.SELECT_SKILL,
    WorkflowState.SELECT_SKILL: WorkflowState.RETRIEVE,
    WorkflowState.RETRIEVE: WorkflowState.CHECK_EVIDENCE,
    WorkflowState.CHECK_EVIDENCE: WorkflowState.GENERATE_CLAIMS,
    WorkflowState.GENERATE_CLAIMS: WorkflowState.VERIFY_CLAIMS,
    WorkflowState.VERIFY_CLAIMS: WorkflowState.FINALIZE,
    WorkflowState.FINALIZE: WorkflowState.END,
}


class AgentStateMachine:
    """Explicit state transition guard with fail-closed finalization shortcuts."""

    def __init__(self, run: AgentRun) -> None:
        self.run = run

    @property
    def state(self) -> WorkflowState:
        return self.run.state

    def transition(self, target: WorkflowState, *, fail_closed: bool = False) -> None:
        source = self.state
        if source is WorkflowState.END:
            raise InvalidStateTransition("END is terminal")

        allowed = NORMAL_NEXT_STATE.get(source) is target
        fail_closed_shortcut = fail_closed and target is WorkflowState.FINALIZE
        if not (allowed or fail_closed_shortcut):
            raise InvalidStateTransition(f"invalid transition: {source} -> {target}")
        self.run.state = target
