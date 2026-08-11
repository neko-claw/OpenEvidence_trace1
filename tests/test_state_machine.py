import pytest

from a5.agent.state import AgentStateMachine, InvalidStateTransition
from a5.domain.enums import WorkflowState
from a5.domain.models import AgentRun, Question
from a5.runtime_config import load_runtime_config


def make_machine() -> AgentStateMachine:
    config = load_runtime_config()
    return AgentStateMachine(
        AgentRun(
            question=Question(text="fixture"),
            agent_version=config.agent.agent_version,
            gate_config_version=config.gates.config_version,
            runtime_config_snapshot=config.snapshot(),
        )
    )


def test_normal_state_path_is_explicit_and_terminal() -> None:
    machine = make_machine()
    path = [
        WorkflowState.GATE0,
        WorkflowState.CLASSIFY,
        WorkflowState.SELECT_SKILL,
        WorkflowState.PLAN,
        WorkflowState.RETRIEVE,
        WorkflowState.GATE1,
        WorkflowState.GATE2,
        WorkflowState.SUMMARIZE_EVIDENCE,
        WorkflowState.GENERATE_CLAIMS,
        WorkflowState.CLAIM_SPLITTER,
        WorkflowState.AUDIT_CITATIONS,
        WorkflowState.GATE5,
        WorkflowState.GATE6,
        WorkflowState.FINALIZE,
        WorkflowState.END,
    ]
    for state in path:
        machine.transition(state)
    assert machine.state is WorkflowState.END


def test_gate2_retry_loop_is_explicit() -> None:
    machine = make_machine()
    for state in (
        WorkflowState.GATE0,
        WorkflowState.CLASSIFY,
        WorkflowState.SELECT_SKILL,
        WorkflowState.PLAN,
        WorkflowState.RETRIEVE,
        WorkflowState.GATE1,
        WorkflowState.GATE2,
        WorkflowState.RETRIEVE,
        WorkflowState.GATE1,
        WorkflowState.GATE2,
    ):
        machine.transition(state)
    assert machine.state is WorkflowState.GATE2


def test_invalid_jump_and_terminal_transition_are_rejected() -> None:
    machine = make_machine()
    with pytest.raises(InvalidStateTransition):
        machine.transition(WorkflowState.RETRIEVE)
    machine.transition(WorkflowState.GATE6, fail_closed=True)
    machine.transition(WorkflowState.FINALIZE)
    machine.transition(WorkflowState.END)
    with pytest.raises(InvalidStateTransition):
        machine.transition(WorkflowState.FINALIZE)
