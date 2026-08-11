from __future__ import annotations

from a5.agent.workflow import A5Workflow
from a5.domain.models import AgentRun, Question


def answer(question: Question | str, *, workflow: A5Workflow) -> AgentRun:
    """Stable A5 entry point for A6/B4; dependency wiring stays explicit."""

    return workflow.answer(question)
