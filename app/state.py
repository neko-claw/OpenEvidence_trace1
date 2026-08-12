from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from app.contracts import AgentPayload, HistoryItem


def initialize_state(state: MutableMapping[str, Any]) -> None:
    state.setdefault("current_question", "")
    state.setdefault("ask_input", "")
    state.setdefault("current_agent_run", None)
    state.setdefault("history", [])
    state.setdefault("selected_evidence", None)
    state.setdefault("page_index", 0)
    state.setdefault("history_page_index", 0)
    state.setdefault("wiki_page_index", 0)
    state.setdefault("error_state", None)


def store_run(state: MutableMapping[str, Any], payload: AgentPayload) -> None:
    state["current_agent_run"] = payload
    state["error_state"] = None
    state["page_index"] = 0
    state["selected_evidence"] = None
    history: list[HistoryItem] = list(state.get("history", []))
    history.insert(0, HistoryItem(
        run_id=payload.run_id,
        question=payload.question,
        decision=payload.decision,
        created_at=payload.finished_at or payload.started_at,
        payload=payload,
    ))
    state["history"] = history[:50]


def restore_history_item(state: MutableMapping[str, Any], item: HistoryItem) -> None:
    state["current_question"] = item.question
    state["current_agent_run"] = item.payload
    state["error_state"] = None
    state["page_index"] = 0
