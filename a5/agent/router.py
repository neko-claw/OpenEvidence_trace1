from __future__ import annotations

from a5.domain.enums import WorkflowState
from a5.runtime_config import RuntimeConfig


class SkillRouter:
    """State-aware router; versions come exclusively from runtime config."""

    def __init__(self, runtime_config: RuntimeConfig) -> None:
        self._config = runtime_config

    def route(self, state: WorkflowState, question_type: str) -> str:
        del question_type  # hook for A1 per-question routing rules
        if state in {WorkflowState.CLASSIFY, WorkflowState.PLAN, WorkflowState.RETRIEVE}:
            selected = self._config.skills.evidence_research
            return f"evidence_research@{selected.version}"
        if state in {WorkflowState.CLAIM_SPLITTER, WorkflowState.AUDIT_CITATIONS, WorkflowState.GATE5}:
            selected = self._config.skills.citation_audit
            return f"citation_audit@{selected.version}"
        raise ValueError(f"no Skill route for state {state}")
