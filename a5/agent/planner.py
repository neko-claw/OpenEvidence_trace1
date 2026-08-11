from __future__ import annotations

from a5.domain.models import AgentPlan, Question
from a5.skills.evidence_research import EvidenceResearchSkill


class AgentPlanner:
    """Thin boundary that keeps configurable research policy out of Workflow."""

    def __init__(self, research_skill: EvidenceResearchSkill) -> None:
        self._research_skill = research_skill

    def classify(self, question: Question) -> str:
        return self._research_skill.classify(question)

    def create_plan(self, question: Question) -> AgentPlan:
        return self._research_skill.plan(question)
