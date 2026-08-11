from __future__ import annotations

from dataclasses import dataclass, field

from a5.domain.models import AgentPlan, Question, SearchPlan


@dataclass(frozen=True)
class ResearchRule:
    preferred_sources: tuple[str, ...]
    expected_evidence_types: tuple[str, ...]
    freshness_required: bool
    max_tool_calls: int


def _default_rules() -> dict[str, ResearchRule]:
    return {
        "treatment_evidence": ResearchRule(
            preferred_sources=("guideline", "systematic_review", "primary_study"),
            expected_evidence_types=("guideline", "systematic_review", "controlled_study"),
            freshness_required=True,
            max_tool_calls=3,
        ),
        "diagnostic_evidence": ResearchRule(
            preferred_sources=("guideline", "systematic_review", "diagnostic_study"),
            expected_evidence_types=("guideline", "diagnostic_accuracy_study"),
            freshness_required=True,
            max_tool_calls=3,
        ),
        "general_evidence": ResearchRule(
            preferred_sources=("guideline", "systematic_review", "primary_study"),
            expected_evidence_types=("guideline", "review", "study"),
            freshness_required=False,
            max_tool_calls=2,
        ),
    }


@dataclass(frozen=True)
class QuestionClassifierConfig:
    """TEMPORARY DEFAULT POLICY; replace with A1-owned configuration."""

    version: str = "temporary-a1-default-v0.1"
    keyword_types: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "treatment_evidence": ("treat", "therapy", "intervention", "治疗", "用药"),
            "diagnostic_evidence": ("diagnos", "test", "screen", "诊断", "筛查"),
        }
    )
    rules: dict[str, ResearchRule] = field(default_factory=_default_rules)
    fallback_type: str = "general_evidence"


class EvidenceResearchSkill:
    name = "evidence_research"
    version = "0.1"

    def __init__(self, config: QuestionClassifierConfig | None = None) -> None:
        self.config = config or QuestionClassifierConfig()

    @property
    def identifier(self) -> str:
        return f"{self.name}@v{self.version}"

    def classify(self, question: Question) -> str:
        normalized = question.text.casefold()
        for question_type, keywords in self.config.keyword_types.items():
            if any(keyword.casefold() in normalized for keyword in keywords):
                return question_type
        return self.config.fallback_type

    def plan(self, question: Question) -> AgentPlan:
        question_type = self.classify(question)
        rule = self.config.rules[question_type]
        return AgentPlan(
            question_type=question_type,
            selected_skill=self.identifier,
            search_plan=SearchPlan(
                queries=[question.text],
                preferred_sources=list(rule.preferred_sources),
                freshness_required=rule.freshness_required,
                expected_evidence_types=list(rule.expected_evidence_types),
                max_tool_calls=rule.max_tool_calls,
            ),
            policy_version=self.config.version,
        )
