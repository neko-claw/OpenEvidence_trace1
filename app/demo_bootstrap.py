from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from app.services.agent_service import get_agent_service
from app.state import store_run


def bootstrap_replay_from_query(
    state: MutableMapping[str, Any],
    query_params: MutableMapping[str, Any],
) -> None:
    """Load an A5 replay for deterministic demos/screenshots, at most once."""

    if state.get("autorun_complete") or query_params.get("autorun") != "1":
        return
    case = str(query_params.get("case", "PASS")).upper()
    if case not in {"PASS", "WARN", "REFUSE", "ERROR"}:
        return
    question = str(query_params.get("question", "Demo evidence question"))
    state["autorun_complete"] = True
    state["demo_case"] = case
    state["current_question"] = question
    state["ask_input"] = question
    payload = get_agent_service().analyze(question, mode="replay", replay_case=case)
    store_run(state, payload)
