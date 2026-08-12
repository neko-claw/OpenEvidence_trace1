"""A4 -> A5 evidence retriever adapter.

Implements the main repository's ``a5.ports.EvidenceRetriever`` protocol:

    retrieve(question, plan, request) -> a5.domain.models.RetrievalResult

using A5's real Pydantic types (``a5.domain.models``) and A4's native
``RetrievalService``.  A4 never defines, renames, or shadows A5 public
contracts; everything A5 sees here is a real ``a5.domain.models`` object.

Contract rules enforced by this adapter:

- ``request.source_type`` restricts this tool call's candidates; a non-empty
  value that matches no candidate yields an empty (never fabricated) result.
- ``request.tool_call_index`` is recorded in ``diagnostics`` so A5 multi-source
  retries and Tool Budget remain observable.
- ``SearchResult.status`` (ok/partial/empty/failed) is never upgraded:
  partial/empty/failed results are reported as-is in ``diagnostics["status"]``
  and degraded evidence is returned (possibly empty).
- ``EvidenceRecord.spans`` is only populated from real A3 spans.  The A3 Span
  Schema is pending, so spans stay ``[]`` and
  ``diagnostics["span_status"] == "UNKNOWN_A3_PENDING"``; no span ID is ever
  synthesized.
- A4's token-overlap alignment hints go into ``diagnostics`` only and are
  never mapped to ``VerificationStatus.SUPPORTED`` (that is A5 Gate5's job).
- Upstream provenance hashes (``evidence_content_hash``, ``content_hash``)
  are preserved verbatim; missing provenance is reported as UNKNOWN, never
  fabricated.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from hashlib import sha256
import json
from typing import Any

from a5.domain.models import (
    EvidenceRecord,
    EvidenceSpan,
    Question,
    RetrievalRequest,
    RetrievalResult,
    SearchPlan,
)
from a5.domain.enums import RetrievalScoreKind, RetrievalScoreScope
from a5.ports.evidence_retriever import EvidenceRetriever

from retrieval.config import RetrievalConfig
from retrieval.models import Query, SearchResult, SearchStatus
from retrieval.ports import RetrievalServicePort
from retrieval.query_plan import parse_query

# Optional A3 span provider: chunk_id -> sequence of real A3 spans.  A3's
# EvidenceSpan schema is authoritative (contracts/a3/v0.2); A4 never invents a
# span schema or span IDs.  The provider may return any object exposing
# span_id/text/chunk_id/page/section (duck-typed) so the adapter stays decoupled
# from ``a3.domain.models`` imports while remaining compatible with them.
SpanProvider = Callable[[str], Sequence[Any]]


class A4EvidenceRetrieverAdapter:
    """Adapter: ``a5.ports.EvidenceRetriever`` backed by A4's ``RetrievalService``.

    ``span_provider`` wires real A3 spans: when provided, selected chunks get
    their real A3 spans mapped onto ``EvidenceRecord.spans`` and
    ``diagnostics["span_status"] == "A3_AVAILABLE"``; without it, spans stay
    empty and ``span_status == "UNKNOWN_A3_PENDING"``.  Span IDs are never
    synthesized.
    """

    def __init__(
        self,
        service: RetrievalServicePort,
        config: RetrievalConfig | None = None,
        *,
        tool_name: str = "a4_evidence_retrieval",
        span_provider: SpanProvider | None = None,
    ) -> None:
        if not callable(getattr(service, "search", None)):
            raise ValueError("service must provide a callable search method")
        if config is not None and not isinstance(config, RetrievalConfig):
            raise ValueError("config must be a RetrievalConfig or None")
        if span_provider is not None and not callable(span_provider):
            raise ValueError("span_provider must be callable or None")
        self._service = service
        self._config = config if config is not None else RetrievalConfig()
        self._tool_name = tool_name
        self._span_provider = span_provider
        self.call_count = 0

    @property
    def service(self) -> RetrievalServicePort:
        return self._service

    def retrieve(
        self,
        question: Question,
        plan: SearchPlan,
        request: RetrievalRequest,
    ) -> RetrievalResult:
        """One bounded A5 tool call normalized to the A5 RetrievalResult view."""
        self.call_count += 1
        query = self._build_query(question, plan, request)
        result = self._service.search(query)
        return self._to_retrieval_result(question, plan, request, query, result)

    # -- mapping helpers ------------------------------------------------------

    def _build_query(
        self,
        question: Question,
        plan: SearchPlan,
        request: RetrievalRequest,
    ) -> Query:
        """Native A4 Query from the real A5 types (defensive out-of-scope scan)."""
        native = parse_query(question.question_id, question.text).to_query()
        metadata = question.metadata or {}
        return Query(
            query_id=question.question_id,
            text=question.text,
            language="zh",
            pico_population=native.pico_population,
            pico_intervention=native.pico_intervention,
            pico_comparator=native.pico_comparator,
            pico_outcome=native.pico_outcome,
            as_of_date=native.as_of_date,
            topic=metadata.get("topic", native.topic),
            question_type=metadata.get("question_type", native.question_type),
            freshness=metadata.get("freshness", native.freshness),
            english_terms=tuple(plan.queries) or native.english_terms,
            source_types=(request.source_type,) if request.source_type not in {"", "*"} else (),
            evidence_levels=tuple(metadata.get("evidence_levels", ())),
            atomic_claims=tuple(metadata.get("atomic_claims", native.atomic_claims)),
            domain=metadata.get("domain", native.domain),
            out_of_scope=bool(metadata.get("out_of_scope", False)) or native.out_of_scope,
        )

    def _to_retrieval_result(
        self,
        question: Question,
        plan: SearchPlan,
        request: RetrievalRequest,
        query: Query,
        result: SearchResult,
    ) -> RetrievalResult:
        evidence = [
            record
            for chunk, quality_score, ranking_score in self._selected_with_scores(result)
            if (
                record := self._to_evidence_record(
                    chunk, quality_score, ranking_score, result
                )
            ) is not None
        ]
        diagnostics = self._build_diagnostics(question, plan, request, result, query)
        return RetrievalResult(
            evidence=evidence,
            tool_name=self._tool_name,
            diagnostics=diagnostics,
        )

    def _selected_with_scores(
        self, result: SearchResult
    ) -> list[tuple[Any, float | None, float | None]]:
        """Return separate calibrated quality and query-local ranking scores.

        A4 ranking values are diagnostic only.  They must never be clamped or
        relabeled as Gate2 evidence-quality probabilities.
        """
        ranking_by_id: dict[str, float] = {}
        for log in result.rank_log:
            if log.candidate is None or log.candidate.chunk.chunk_id not in {
                chunk.chunk_id for chunk in result.selected_chunks
            }:
                continue
            score = log.candidate.rerank_score
            if score is not None:
                ranking_by_id[log.candidate.chunk.chunk_id] = float(score)
        quality_by_id = (
            dict(result.quality_scores)
            if result.quality_score_kind == "QUALITY"
            and result.quality_score_scope == "CROSS_QUERY"
            and result.quality_score_calibrated is True
            else {}
        )
        return [
            (
                chunk,
                quality_by_id.get(chunk.chunk_id),
                ranking_by_id.get(chunk.chunk_id),
            )
            for chunk in result.selected_chunks
        ]

    def _citation_id(self, chunk: Any) -> str:
        """Frozen citation-ID rule (config.citation_id_rule)."""
        rule = self._config.citation_id_rule
        if rule == "evidence_id::chunk_id":
            return f"{chunk.evidence_id}::{chunk.chunk_id}"
        if rule == "chunk_id":
            return chunk.chunk_id
        if rule == "evidence_id":
            return chunk.evidence_id
        raise ValueError(f"unsupported citation_id_rule: {rule!r}")

    def _to_evidence_record(
        self,
        chunk: Any,
        quality_score: float | None,
        ranking_score: float | None,
        result: SearchResult,
    ) -> EvidenceRecord:
        """Map one A4 chunk onto the narrow A5 ``EvidenceRecord`` view."""
        published_at: datetime | None = None
        if isinstance(chunk.published_at, str):
            try:
                published_at = datetime.fromisoformat(chunk.published_at.replace("Z", "+00:00"))
            except ValueError:
                published_at = None
        conflicts = sorted(
            {
                evidence_id
                for left, right, _reason in result.conflicts
                for evidence_id in (left, right)
                if evidence_id == chunk.evidence_id
            }
        )
        spans = self._a3_spans_for(chunk)
        return EvidenceRecord(
            id=self._citation_id(chunk),
            content=chunk.text,
            source_type=chunk.source_type,
            title=chunk.title or chunk.stable_id,
            source_metadata={
                "citation_id": self._citation_id(chunk),
                "evidence_id": chunk.evidence_id,
                "chunk_id": chunk.chunk_id,
                "stable_id": chunk.stable_id,
                "index_version": chunk.index_version,
                "corpus_version": chunk.corpus_version,
                "chunk_policy_version": chunk.chunk_policy_version,
                "embedding_model": chunk.embedding_model,
                "embedding_revision": chunk.embedding_revision,
                "evidence_content_hash": chunk.evidence_content_hash,
                "chunk_content_hash": chunk.content_hash,
                "provenance_unknown": not chunk.provenance_complete,
                "page": chunk.page,
                "section": chunk.section,
                "ranking_score": ranking_score,
                "ranking_score_kind": result.ranking_score_kind,
                "ranking_score_scope": result.ranking_score_scope,
                "ranking_score_calibrated": result.ranking_score_calibrated,
            },
            population=", ".join(chunk.pico_population) or None,
            intervention=", ".join(chunk.pico_intervention) or None,
            comparator=", ".join(chunk.pico_comparator) or None,
            outcome=", ".join(chunk.pico_outcome) or None,
            published_at=published_at,
            retrieval_score=quality_score,
            retrieval_score_kind=(
                RetrievalScoreKind.QUALITY
                if quality_score is not None
                else RetrievalScoreKind.UNKNOWN
            ),
            retrieval_score_scope=(
                RetrievalScoreScope.CROSS_QUERY
                if quality_score is not None
                else RetrievalScoreScope.UNKNOWN
            ),
            retrieval_score_calibrated=True if quality_score is not None else None,
            evidence_level=chunk.evidence_level,
            spans=spans,
            conflicts_with_ids=conflicts,
            mock=chunk.mock,
        )

    def _a3_spans_for(self, chunk: Any) -> list[EvidenceSpan]:
        """Real A3 spans only; never synthesized (A3 Span Schema is authoritative)."""
        if self._span_provider is None:
            return []
        spans: list[EvidenceSpan] = []
        for raw in self._span_provider(chunk.chunk_id) or ():
            span_id = getattr(raw, "span_id", None)
            text = getattr(raw, "text", None)
            if not span_id or not text:
                continue  # 缺字段的 span 保持缺席，不猜测
            spans.append(
                EvidenceSpan(
                    span_id=str(span_id),
                    text=str(text),
                    chunk_id=getattr(raw, "chunk_id", None) or chunk.chunk_id,
                    page=getattr(raw, "page", None),
                    section=getattr(raw, "section", None),
                )
            )
        return spans

    def _build_diagnostics(
        self,
        question: Question,
        plan: SearchPlan,
        request: RetrievalRequest,
        result: SearchResult,
        query: Query,
    ) -> dict[str, Any]:
        provenance_unknown = [
            chunk.chunk_id
            for chunk in result.selected_chunks
            if not chunk.provenance_complete
        ]
        diagnostics: dict[str, Any] = {
            "adapter": type(self).__name__,
            "tool_call_index": request.tool_call_index,
            "requested_source": request.source_type,
            "query_count": len(plan.queries),
            "status": result.status.value,
            "degradation_reasons": list(result.degradation_reasons),
            "degradation_codes": list(result.degradation_codes),
            "retrieval_warning": result.retrieval_warning,
            "latency_ms": result.latency_ms,
            "stage_latency_ms": dict(result.stage_latency_ms),
            "versions": {
                "index_version": result.index_version,
                "corpus_version": result.corpus_version,
                "rerank_config_version": result.rerank_config_version,
                "reason_code_version": result.reason_code_version,
            },
            "ranking_score_semantics": {
                "kind": result.ranking_score_kind,
                "scope": result.ranking_score_scope,
                "calibrated": result.ranking_score_calibrated,
            },
            "quality_score_semantics": {
                "kind": result.quality_score_kind,
                "scope": result.quality_score_scope,
                "calibrated": result.quality_score_calibrated,
                "count": len(result.quality_scores),
            },
            "run_hash": result.run_hash,
            "config_snapshot": self._config_snapshot(),
            "config_hash": self._config_hash(),
            "span_status": "A3_AVAILABLE" if self._span_provider is not None else "UNKNOWN_A3_PENDING",
            "span_provider": self._span_provider is not None,
            "alignment_hints": [
                {
                    "claim_index": hint.claim_index,
                    "claim_text": hint.claim_text,
                    "decision": hint.decision,
                    "evidence_ids": list(hint.evidence_ids),
                    "reason": hint.reason,
                    "method": hint.method,
                    "threshold_version": hint.threshold_version,
                }
                for hint in result.alignment_hints
            ],
            "out_of_scope": query.out_of_scope,
        }
        if provenance_unknown:
            diagnostics["provenance_unknown_chunks"] = provenance_unknown
        if result.status in {SearchStatus.PARTIAL, SearchStatus.EMPTY, SearchStatus.FAILED}:
            diagnostics["degraded"] = True
        return diagnostics

    def _config_snapshot(self) -> dict[str, Any]:
        config = self._config
        return {
            "rerank_config_version": config.rerank_config_version,
            "index_version": config.index_version,
            "corpus_version": config.corpus_version,
            "selection_top_k": config.selection_top_k,
            "mmr_lambda": config.mmr_lambda,
            "low_top_rerank_score": config.low_top_rerank_score,
            "default_as_of_date": config.default_as_of_date,
            "citation_id_rule": config.citation_id_rule,
            "alignment_threshold_version": config.alignment_threshold_version,
            "reason_code_version": config.reason_code_version,
            "weights": {
                "semantic": config.feature_weights.semantic,
                "lexical": config.feature_weights.lexical,
                "pico_match": config.feature_weights.pico_match,
                "evidence_level": config.feature_weights.evidence_level,
                "freshness": config.feature_weights.freshness,
                "source_reliability": config.feature_weights.source_reliability,
            },
        }

    def _config_hash(self) -> str:
        canonical = json.dumps(
            self._config_snapshot(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return sha256(canonical.encode("utf-8")).hexdigest()
