from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from a5.domain.enums import (
    ClaimCriticality,
    Decision,
    SafetyStatus,
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
    """Smallest structural surface used by A5 compatibility adapters."""

    id: str
    content: str


class EvidenceRecord(StrictModel):
    """TEMPORARY COMPATIBILITY MODEL.

    This is not the final A2/A3 Evidence schema. Real upstream evidence must be
    converted into this narrow A5 view by an adapter.
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
    mock: bool = False


class SearchPlan(StrictModel):
    queries: list[str] = Field(min_length=1)
    preferred_sources: list[str] = Field(min_length=1)
    freshness_required: bool = False
    expected_evidence_types: list[str] = Field(min_length=1)
    max_tool_calls: int = Field(default=3, ge=1, le=20)


class AgentPlan(StrictModel):
    question_type: str
    selected_skill: str
    search_plan: SearchPlan
    policy_version: str


class Claim(StrictModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    criticality: ClaimCriticality
    evidence_ids: list[str] = Field(default_factory=list)
    uncertainty: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value


class VerificationResult(StrictModel):
    claim_id: str
    status: VerificationStatus
    checked_evidence_ids: list[str] = Field(default_factory=list)
    illegal_evidence_ids: list[str] = Field(default_factory=list)
    reason: str
    verifier: str


class CitationAuditReport(StrictModel):
    decision: Decision
    verification_results: list[VerificationResult] = Field(default_factory=list)
    approved_claim_ids: list[str] = Field(default_factory=list)
    rejected_claim_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class SafetyAssessment(StrictModel):
    status: SafetyStatus
    reason: str
    policy_version: str


class RetrievalResult(StrictModel):
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    tool_name: str
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ToolTrace(StrictModel):
    state: WorkflowState
    timestamp: datetime = Field(default_factory=utc_now)
    selected_skill: str | None = None
    agent_plan: dict[str, Any] | None = None
    tool: str | None = None
    tool_input_summary: dict[str, Any] | None = None
    tool_output_count: int | None = None
    retrieved_evidence_ids: list[str] = Field(default_factory=list)
    generated_claim_ids: list[str] = Field(default_factory=list)
    verification_result: dict[str, str] = Field(default_factory=dict)
    final_decision: Decision | None = None
    latency_ms: float = Field(default=0.0, ge=0.0)
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class FinalAnswer(StrictModel):
    decision: Decision
    text: str
    included_claim_ids: list[str] = Field(default_factory=list)
    cited_evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AgentRun(StrictModel):
    run_id: str = Field(default_factory=lambda: f"RUN-{uuid4().hex[:12]}")
    question: Question
    state: WorkflowState = WorkflowState.CLASSIFY
    selected_skill: str | None = None
    agent_plan: AgentPlan | None = None
    safety_assessment: SafetyAssessment | None = None
    retrieved_evidence: list[EvidenceRecord] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    verification_results: list[VerificationResult] = Field(default_factory=list)
    final_answer: FinalAnswer | None = None
    decision: Decision | None = None
    trace: list[ToolTrace] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    latency_ms: float | None = Field(default=None, ge=0.0)
    error: str | None = None
