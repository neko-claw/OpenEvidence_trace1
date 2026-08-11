from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from a5.domain.enums import (
    ClaimCriticality,
    Decision,
    EventType,
    FreshnessState,
    MatchStatus,
    RecommendedAction,
    SafetyDecision,
    SufficiencyStatus,
    UncertaintyLevel,
    VerificationStatus,
    WorkflowState,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Question(StrictModel):
    question_id: str = Field(default_factory=lambda: f"Q-{uuid4().hex[:12]}")
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question text must not be blank")
        return normalized


@runtime_checkable
class EvidenceLike(Protocol):
    """Small structural surface consumed by an A2/A3 compatibility adapter."""

    id: str
    content: str


class EvidenceSpan(StrictModel):
    span_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    chunk_id: str | None = None
    page: int | None = Field(default=None, ge=1)
    section: str | None = None


class EvidenceRecord(StrictModel):
    """TEMPORARY COMPATIBILITY MODEL, not the frozen A2/A3 schema.

    Upstream records must be normalized to this narrow view by an adapter.
    Missing quality/provenance fields stay ``None`` and gates treat them as
    UNKNOWN; A5 never manufactures scores, evidence levels, spans, or dates.
    """

    id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    published_at: datetime | None = None
    retrieval_score: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_level: str | None = None
    spans: list[EvidenceSpan] = Field(default_factory=list)
    conflicts_with_ids: list[str] = Field(default_factory=list)
    mock: bool = False


class EvidenceSummary(StrictModel):
    evidence_count: int = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    source_diversity: float | None = Field(default=None, ge=0.0, le=1.0)
    strongest_evidence_level: str | None = None
    freshness_summary: FreshnessState = FreshnessState.UNKNOWN
    conflicts_detected: bool = False
    summary_text: str


class SearchPlan(StrictModel):
    queries: list[str] = Field(min_length=1)
    preferred_sources: list[str] = Field(min_length=1)
    freshness_required: bool = False
    expected_evidence_types: list[str] = Field(min_length=1)
    max_tool_calls: int = Field(ge=1, le=20)


class AgentPlan(StrictModel):
    question_type: str
    selected_skill: str
    search_plan: SearchPlan
    policy_version: str
    evidence_summary: EvidenceSummary | None = None


class RetrievalRequest(StrictModel):
    source_type: str
    tool_call_index: int = Field(ge=1)


class Claim(StrictModel):
    claim_id: str = Field(min_length=1)
    run_id: str = ""
    text: str = Field(min_length=1)
    criticality: ClaimCriticality
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_span_ids: list[str] = Field(default_factory=list)
    uncertainty: UncertaintyLevel = UncertaintyLevel.UNKNOWN
    entailment_score: float | None = Field(default=None, ge=0.0, le=1.0)
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    as_of_date: date | None = None
    population_match: MatchStatus = MatchStatus.UNKNOWN
    intervention_match: MatchStatus = MatchStatus.UNKNOWN
    comparator_match: MatchStatus = MatchStatus.UNKNOWN
    outcome_match: MatchStatus = MatchStatus.UNKNOWN
    time_match: MatchStatus = MatchStatus.UNKNOWN
    conflict_ids: list[str] = Field(default_factory=list)
    verification_method: str | None = None
    decision: VerificationStatus | None = None

    @field_validator("evidence_ids", "evidence_span_ids", "conflict_ids")
    @classmethod
    def ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("identifier lists must contain unique values")
        return value


class VerificationContext(StrictModel):
    freshness_required: bool = False
    run_date: date = Field(default_factory=lambda: utc_now().date())


class TextualSupportAssessment(StrictModel):
    status: VerificationStatus
    entailment_score: float | None = Field(default=None, ge=0.0, le=1.0)
    method: str
    reason: str


class VerificationResult(StrictModel):
    claim_id: str
    status: VerificationStatus
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_span_ids: list[str] = Field(default_factory=list)
    checked_evidence_ids: list[str] = Field(default_factory=list)
    illegal_evidence_ids: list[str] = Field(default_factory=list)
    illegal_span_ids: list[str] = Field(default_factory=list)
    citation_valid: bool = False
    span_check: MatchStatus = MatchStatus.UNKNOWN
    population_match: MatchStatus = MatchStatus.UNKNOWN
    intervention_match: MatchStatus = MatchStatus.UNKNOWN
    comparator_match: MatchStatus = MatchStatus.UNKNOWN
    outcome_match: MatchStatus = MatchStatus.UNKNOWN
    time_match: MatchStatus = MatchStatus.UNKNOWN
    entailment_score: float | None = Field(default=None, ge=0.0, le=1.0)
    conflict_ids: list[str] = Field(default_factory=list)
    uncertainty: UncertaintyLevel = UncertaintyLevel.UNKNOWN
    verification_method: str
    reasons: list[str] = Field(default_factory=list)

    @property
    def reason(self) -> str:
        """Backward-compatible readable reason."""
        return "; ".join(self.reasons)

    @property
    def verifier(self) -> str:
        """Backward-compatible verifier alias."""
        return self.verification_method


class CitationAuditReport(StrictModel):
    decision: Decision
    verification_results: list[VerificationResult] = Field(default_factory=list)
    approved_claim_ids: list[str] = Field(default_factory=list)
    rejected_claim_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class SafetyAssessment(StrictModel):
    decision: SafetyDecision
    reason: str
    policy_version: str


class RetrievalResult(StrictModel):
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    tool_name: str
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class EvidenceSufficiencyMetrics(StrictModel):
    candidate_count: int = Field(ge=0)
    top_score: float | None = Field(default=None, ge=0.0, le=1.0)
    source_type_count: int = Field(ge=0)
    source_diversity: float | None = Field(default=None, ge=0.0, le=1.0)
    strongest_evidence_level: str | None = None
    freshness_state: FreshnessState
    conflict_count: int = Field(ge=0)


class EvidenceSufficiencyResult(StrictModel):
    status: SufficiencyStatus
    reasons: list[str] = Field(default_factory=list)
    metrics: EvidenceSufficiencyMetrics
    recommended_action: RecommendedAction


class ToolBudgetSnapshot(StrictModel):
    max_tool_calls: int = Field(ge=0)
    used_tool_calls: int = Field(ge=0)
    remaining_tool_calls: int = Field(ge=0)
    budget_exhausted: bool


class ToolTrace(StrictModel):
    run_id: str
    state: WorkflowState
    event_type: EventType
    timestamp: datetime = Field(default_factory=utc_now)
    gate: str | None = None
    skill: str | None = None
    tool: str | None = None
    tool_call_index: int | None = Field(default=None, ge=1)
    tool_budget_remaining: int | None = Field(default=None, ge=0)
    input_summary: dict[str, Any] | None = None
    output_count: int | None = Field(default=None, ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    decision: str | None = None
    latency_ms: float = Field(default=0.0, ge=0.0)
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    # Compatibility aliases for the original A6/B4 demo contract.
    @property
    def selected_skill(self) -> str | None:
        return self.skill

    @property
    def retrieved_evidence_ids(self) -> list[str]:
        return self.evidence_ids

    @property
    def generated_claim_ids(self) -> list[str]:
        return self.claim_ids

    @property
    def final_decision(self) -> Decision | None:
        try:
            return Decision(self.decision) if self.decision else None
        except ValueError:
            return None


class FinalAnswer(StrictModel):
    decision: Decision
    text: str
    included_claim_ids: list[str] = Field(default_factory=list)
    cited_evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RuntimeConfigSnapshot(StrictModel):
    agent: dict[str, Any]
    gates: dict[str, Any]
    skills: dict[str, Any]
    models: dict[str, Any]


class AgentRun(StrictModel):
    run_id: str = Field(default_factory=lambda: f"RUN-{uuid4().hex[:12]}")
    question: Question
    state: WorkflowState = WorkflowState.START
    selected_skill: str | None = None
    selected_skills: list[str] = Field(default_factory=list)
    agent_plan: AgentPlan | None = None
    safety_assessment: SafetyAssessment | None = None
    evidence_sufficiency: EvidenceSufficiencyResult | None = None
    evidence_summary: EvidenceSummary | None = None
    retrieved_evidence: list[EvidenceRecord] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    verification_results: list[VerificationResult] = Field(default_factory=list)
    final_answer: FinalAnswer | None = None
    decision: Decision | None = None
    trace: list[ToolTrace] = Field(default_factory=list)
    agent_version: str
    skill_versions: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    gate_config_version: str
    runtime_config_snapshot: RuntimeConfigSnapshot
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    latency_ms: float | None = Field(default=None, ge=0.0)
    error: str | None = None


class EvidenceResearchInput(StrictModel):
    question: Question


class EvidenceResearchOutput(StrictModel):
    question_type: str
    search_queries: list[str] = Field(min_length=1)
    preferred_sources: list[str] = Field(min_length=1)
    freshness_required: bool
    expected_evidence_types: list[str] = Field(min_length=1)
    max_tool_calls: int = Field(ge=1)
    evidence_summary: EvidenceSummary


class CitationAuditInput(StrictModel):
    claims: list[Claim]
    evidence: list[EvidenceRecord]
    context: VerificationContext = Field(default_factory=VerificationContext)


class CitationAuditOutput(StrictModel):
    atomic_claims: list[Claim]
    report: CitationAuditReport
