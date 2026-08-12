from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from typing import Any

import streamlit as st

# Architecture boundary: this is the only A6 module allowed to import A5 or the
# A1-A5 deployment facade.
from a5.facade import BackendDependencies, answer_text, to_ui_view
from deployment.track1_backend import BackendService, build_service

from app.contracts import (
    AgentPayload,
    BackendMode,
    DemoCase,
    EvidenceView,
    FindingView,
    SpanView,
    StructuredAnswerView,
    TraceEventView,
)

_SAFE_METADATA_KEYS = {
    "publisher", "journal", "language", "version", "document_version",
    "source_name", "mock_route", "publication_types", "citation_id",
}


@dataclass(frozen=True)
class AgentService:
    """Thin A6 client for A5's stable public API, with no business decisions."""

    live_dependencies: BackendDependencies | None = None
    backend_service: BackendService | None = None

    def analyze(
        self,
        question: str,
        *,
        mode: BackendMode | None = None,
        replay_case: DemoCase = "PASS",
    ) -> AgentPayload:
        effective_mode: BackendMode = mode or (
            self.backend_service.mode if self.backend_service is not None else "research"
        )
        if self.backend_service is not None:
            if effective_mode != self.backend_service.mode:
                raise ValueError("requested mode does not match configured backend service")
            run = self.backend_service.answer(question, replay_case=replay_case)
        else:
            run = answer_text(
                question,
                mode=effective_mode,
                replay_case=replay_case,
                dependencies=self.live_dependencies,
            )
        ui = to_ui_view(run)
        cards = {card.evidence_id: card for card in ui.evidence_cards}
        evidence_by_id = {item.id: item for item in run.retrieved_evidence}
        included_claims = {
            claim.claim_id: claim for claim in run.claims
            if claim.claim_id in ui.included_claim_ids
        }

        evidence_views: list[EvidenceView] = []
        for evidence_id, card in cards.items():
            source = evidence_by_id.get(evidence_id)
            if source is None:
                continue
            cited_span_ids = {
                span_id for claim in included_claims.values()
                if evidence_id in claim.evidence_ids
                for span_id in claim.evidence_span_ids
            }
            spans = tuple(
                SpanView(
                    span_id=span.span_id,
                    text=span.text,
                    chunk_id=span.chunk_id,
                    page=span.page,
                    section=span.section,
                    locator=_span_locator(span.page, span.section, span.chunk_id),
                )
                for span in source.spans if span.span_id in cited_span_ids
            )
            evidence_views.append(
                EvidenceView(
                    evidence_id=card.evidence_id,
                    title=card.title,
                    source_type=card.source_type,
                    published_at=card.published_at,
                    evidence_level=card.evidence_level,
                    url=card.url,
                    page=card.page,
                    section=card.section,
                    mock=card.mock,
                    spans=spans,
                    source_metadata=_safe_metadata(source.source_metadata, mock=source.mock),
                    version=_first_text(source.source_metadata, "version", "document_version", "content_version"),
                    provenance=_safe_provenance(source.source_metadata, mock=source.mock),
                )
            )

        trace = tuple(
            TraceEventView(
                timestamp=event.timestamp,
                state=event.state.value,
                event_type=event.event_type.value,
                gate=event.gate,
                skill=event.skill,
                tool=event.tool,
                tool_call_index=event.tool_call_index,
                tool_budget_remaining=event.tool_budget_remaining,
                output_count=event.output_count,
                evidence_ids=tuple(event.evidence_ids),
                claim_ids=tuple(event.claim_ids),
                decision=event.decision,
                latency_ms=event.latency_ms,
                error=event.error,
            ) for event in ui.trace
        )
        return AgentPayload(
            run_id=ui.run_id,
            question=question,
            decision=ui.decision.value,
            answer_text=ui.answer_text,
            structured_answer=(
                StructuredAnswerView(
                    direct_answer=run.final_answer.structured.direct_answer,
                    direct_evidence_ids=tuple(
                        run.final_answer.structured.direct_evidence_ids
                    ),
                    findings=tuple(
                        FindingView(
                            finding_id=item.finding_id,
                            statement=item.statement,
                            claim_ids=tuple(item.claim_ids),
                            evidence_ids=tuple(item.evidence_ids),
                            display_statement=item.display_statement,
                            display_language=item.display_language,
                            applicability=item.applicability,
                            certainty=item.certainty,
                        )
                        for item in run.final_answer.structured.findings
                    ),
                    applicability=run.final_answer.structured.applicability,
                    evidence_profile=tuple(run.final_answer.structured.evidence_profile),
                    uncertainties=tuple(run.final_answer.structured.uncertainties),
                    composition_method=run.final_answer.structured.composition_method,
                )
                if run.final_answer and run.final_answer.structured
                else None
            ),
            reason_codes=tuple(item.value for item in ui.reason_codes),
            warnings=tuple(ui.warnings),
            limitations=tuple(ui.limitations),
            evidence=tuple(evidence_views),
            trace=trace,
            demo_mode=effective_mode in {"replay", "mock"},
            error_code=ui.error_code.value if ui.error_code else None,
            error_message=ui.error_message,
            started_at=run.started_at,
            finished_at=run.finished_at,
            latency_ms=run.latency_ms,
            agent_version=run.agent_version,
            skill_versions=dict(run.skill_versions),
            prompt_versions=dict(run.prompt_versions),
            gate_config_version=run.gate_config_version,
        )


@st.cache_resource(show_spinner=False)
def get_agent_service() -> AgentService:
    """Cache only the stateless client, never an AgentRun or final answer."""
    configured = os.environ.get("OPENEVIDENCE_APP_MODE", "research").casefold()
    mode: BackendMode = configured if configured in {"research", "replay", "mock", "live"} else "research"  # type: ignore[assignment]
    return AgentService(backend_service=build_service(mode))


def _span_locator(page: int | None, section: str | None, chunk_id: str | None) -> str | None:
    parts: list[str] = []
    if section:
        parts.append(f"章节 {section}")
    if page:
        parts.append(f"第 {page} 页")
    if chunk_id:
        parts.append(f"分块 {chunk_id}")
    return " · ".join(parts) or None


def _first_text(values: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _safe_metadata(values: Mapping[str, Any], *, mock: bool) -> dict[str, Any]:
    result = {
        key: value for key, value in values.items()
        if key in _SAFE_METADATA_KEYS and isinstance(value, (str, int, float, bool))
    }
    if mock:
        result["data_kind"] = "mock"
    return result


def _safe_provenance(values: Mapping[str, Any], *, mock: bool) -> dict[str, Any]:
    raw = values.get("provenance")
    result: dict[str, Any] = {}
    if isinstance(raw, Mapping):
        for key in ("source", "retrieved_at", "content_hash", "adapter_version"):
            value = raw.get(key)
            if isinstance(value, (str, int, float, bool)):
                result[key] = value
    if mock:
        return {"fixture": True}
    return result
