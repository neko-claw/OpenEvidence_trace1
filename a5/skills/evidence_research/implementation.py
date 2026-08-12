from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from a5.domain.enums import FreshnessState
from a5.domain.models import (
    AgentPlan,
    EvidenceRecord,
    EvidenceResearchOutput,
    EvidenceSummary,
    Question,
    SearchPlan,
)
from a5.runtime_config import RuntimeConfig, load_runtime_config
from a5.skills.loader import LoadedSkill, SkillLoader


class EvidenceResearchSkill:
    """Versioned planning and evidence-summary Skill.

    Question taxonomy/rules are temporary configurable A1 defaults. No medical
    source policy is embedded in the workflow.
    """

    name = "evidence_research"

    def __init__(
        self,
        runtime_config: RuntimeConfig | None = None,
        loader: SkillLoader | None = None,
    ) -> None:
        self.runtime_config = runtime_config or load_runtime_config()
        selection = self.runtime_config.skills.evidence_research
        self.asset: LoadedSkill = (loader or SkillLoader()).load(
            selection.manifest, expected_version=selection.version
        )

    @property
    def version(self) -> str:
        return self.asset.manifest.version

    @property
    def prompt_version(self) -> str:
        return self.asset.manifest.prompt_version

    @property
    def identifier(self) -> str:
        return f"{self.name}@{self.version}"

    def classify(self, question: Question) -> str:
        config = self.runtime_config.skills.classifier
        if question.metadata.get("a1_contract_validated") is True:
            upstream_type = question.metadata.get("question_type")
            if isinstance(upstream_type, str) and upstream_type in config.rules:
                return upstream_type
        normalized = question.text.casefold()
        for question_type, keywords in config.keyword_types.items():
            if any(keyword.casefold() in normalized for keyword in keywords):
                return question_type
        return config.fallback_type

    def plan(self, question: Question) -> AgentPlan:
        question_type = self.classify(question)
        config = self.runtime_config.skills.classifier
        rule = config.rules[question_type]
        configured_max = int(rule["max_tool_calls"])
        max_calls = min(configured_max, self.runtime_config.agent.max_tool_calls)
        return AgentPlan(
            question_type=question_type,
            selected_skill=self.identifier,
            search_plan=SearchPlan(
                queries=[question.text],
                preferred_sources=list(rule["preferred_sources"]),
                freshness_required=bool(rule["freshness_required"]),
                expected_evidence_types=list(rule["expected_evidence_types"]),
                max_tool_calls=max_calls,
            ),
            policy_version=config.policy_version,
            evidence_summary=self.summarize([], freshness_required=bool(rule["freshness_required"])),
        )

    def execute(self, question: Question) -> EvidenceResearchOutput:
        plan = self.plan(question)
        return EvidenceResearchOutput(
            question_type=plan.question_type,
            search_queries=plan.search_plan.queries,
            preferred_sources=plan.search_plan.preferred_sources,
            freshness_required=plan.search_plan.freshness_required,
            expected_evidence_types=plan.search_plan.expected_evidence_types,
            max_tool_calls=plan.search_plan.max_tool_calls,
            evidence_summary=plan.evidence_summary
            or self.summarize([], freshness_required=plan.search_plan.freshness_required),
        )

    def summarize(
        self,
        evidence: Sequence[EvidenceRecord],
        *,
        freshness_required: bool,
        as_of_date: date | None = None,
    ) -> EvidenceSummary:
        unique_sources = sorted({record.source_type for record in evidence})
        diversity = len(unique_sources) / len(evidence) if evidence else None
        accepted = self.runtime_config.gates.gate2.accepted_evidence_levels
        strongest = next(
            (
                level
                for level in accepted
                if any(record.evidence_level == level for record in evidence)
            ),
            None,
        )
        conflict_ids = {
            tuple(sorted((record.id, other_id)))
            for record in evidence
            for other_id in record.conflicts_with_ids
            if any(other.id == other_id for other in evidence)
        }
        if not freshness_required:
            freshness = FreshnessState.NOT_REQUIRED
        elif not evidence or any(record.published_at is None for record in evidence):
            freshness = FreshnessState.UNKNOWN
        else:
            max_age = self.runtime_config.gates.gate2.max_age_days
            reference_date = as_of_date or date.today()
            if any(
                record.published_at.date() > reference_date
                for record in evidence
                if record.published_at is not None
            ):
                freshness = FreshnessState.STALE
                fresh_count = 0
            else:
                fresh_count = sum(
                    (reference_date - record.published_at.date()).days <= max_age
                    for record in evidence
                    if record.published_at is not None
                )
                freshness = (
                    FreshnessState.FRESH
                    if fresh_count / len(evidence)
                    >= self.runtime_config.gates.gate2.min_fresh_fraction
                    else FreshnessState.STALE
                )
        summary_text = (
            "No evidence retrieved; quality fields remain UNKNOWN."
            if not evidence
            else (
                f"{len(evidence)} evidence record(s) from {len(unique_sources)} "
                f"source type(s); strongest level={strongest or 'UNKNOWN'}; "
                f"freshness={freshness.value}; conflicts={len(conflict_ids)}."
            )
        )
        return EvidenceSummary(
            evidence_count=len(evidence),
            evidence_ids=[record.id for record in evidence],
            source_types=unique_sources,
            source_diversity=diversity,
            strongest_evidence_level=strongest,
            freshness_summary=freshness,
            conflicts_detected=bool(conflict_ids),
            summary_text=summary_text,
        )
