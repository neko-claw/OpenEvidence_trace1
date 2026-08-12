from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, TypeVar

DecisionName = Literal["PASS", "WARN", "REFUSE"]
DemoCase = Literal["PASS", "WARN", "REFUSE", "ERROR"]
BackendMode = Literal["research", "replay", "mock", "live"]
T = TypeVar("T")


@dataclass(frozen=True)
class SpanView:
    span_id: str
    text: str
    chunk_id: str | None = None
    page: int | None = None
    section: str | None = None
    locator: str | None = None


@dataclass(frozen=True)
class EvidenceView:
    evidence_id: str
    title: str
    source_type: str
    published_at: datetime | None
    evidence_level: str | None
    url: str | None
    page: int | None
    section: str | None
    mock: bool
    spans: tuple[SpanView, ...] = ()
    source_metadata: dict[str, Any] = field(default_factory=dict)
    version: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def year(self) -> str:
        return str(self.published_at.year) if self.published_at else "年份未知"


@dataclass(frozen=True)
class FindingView:
    finding_id: str
    statement: str
    claim_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    display_statement: str | None
    display_language: str | None
    applicability: str | None
    certainty: str


@dataclass(frozen=True)
class StructuredAnswerView:
    direct_answer: str
    direct_evidence_ids: tuple[str, ...]
    findings: tuple[FindingView, ...]
    applicability: str
    evidence_profile: tuple[str, ...]
    uncertainties: tuple[str, ...]
    composition_method: str


@dataclass(frozen=True)
class TraceEventView:
    timestamp: datetime
    state: str
    event_type: str
    gate: str | None
    skill: str | None
    tool: str | None
    tool_call_index: int | None
    tool_budget_remaining: int | None
    output_count: int | None
    evidence_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]
    decision: str | None
    latency_ms: float
    error: str | None


@dataclass(frozen=True)
class AgentPayload:
    run_id: str
    question: str
    decision: DecisionName
    answer_text: str
    structured_answer: StructuredAnswerView | None
    reason_codes: tuple[str, ...]
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]
    evidence: tuple[EvidenceView, ...]
    trace: tuple[TraceEventView, ...]
    demo_mode: bool  # Internal compatibility flag; never presented as a product mode.
    error_code: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
    latency_ms: float | None
    agent_version: str
    skill_versions: dict[str, str]
    prompt_versions: dict[str, str]
    gate_config_version: str


@dataclass(frozen=True)
class HistoryItem:
    run_id: str
    question: str
    decision: DecisionName
    created_at: datetime
    payload: AgentPayload


@dataclass(frozen=True)
class WikiTopic:
    slug: str
    title: str
    subtitle: str
    summary: str
    related_questions: tuple[str, ...]
    evidence_note: str
