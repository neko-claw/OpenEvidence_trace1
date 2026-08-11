import pytest

from a5.agent.state import AgentStateMachine, InvalidStateTransition
from a5.domain.enums import WorkflowState
from a5.domain.models import AgentRun, Question


def make_machine() -> AgentStateMachine:
    return AgentStateMachine(AgentRun(question=Question(text="fixture")))


def test_normal_state_path_is_explicit_and_terminal() -> None:
    machine = make_machine()
    expected = [
        WorkflowState.PLAN,
        WorkflowState.SELECT_SKILL,
        WorkflowState.RETRIEVE,
        WorkflowState.CHECK_EVIDENCE,
        WorkflowState.GENERATE_CLAIMS,
        WorkflowState.VERIFY_CLAIMS,
        WorkflowState.FINALIZE,
        WorkflowState.END,
    ]
    for state in expected:
        machine.transition(state)
    assert machine.state is WorkflowState.END


def test_invalid_state_jump_is_rejected() -> None:
    machine = make_machine()
    with pytest.raises(InvalidStateTransition):
        machine.transition(WorkflowState.RETRIEVE)


def test_fail_closed_path_can_finalize_early_but_not_end_directly() -> None:
    machine = make_machine()
    machine.transition(WorkflowState.FINALIZE, fail_closed=True)
    machine.transition(WorkflowState.END)
    assert machine.state is WorkflowState.END


def test_end_is_terminal() -> None:
    machine = make_machine()
    machine.transition(WorkflowState.FINALIZE, fail_closed=True)
    machine.transition(WorkflowState.END)
    with pytest.raises(InvalidStateTransition):
        machine.transition(WorkflowState.FINALIZE, fail_closed=True)
