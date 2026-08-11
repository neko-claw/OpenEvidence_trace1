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

from datetime import datetime
from hashlib import sha256
import json
from typing import Any

from a5.domain.models import (
    EvidenceRecord,
    Question,
    RetrievalRequest,
    RetrievalResult,
    SearchPlan,
)
from a5.ports.evidence_retriever import EvidenceRetriever

from retrieval.config import RetrievalConfig
from retrieval.models import Query, SearchResult, SearchStatus
from retrieval.ports import RetrievalServicePort
from retrieval.query_plan import parse_query


class A4EvidenceRetrieverAdapter:
    """Adapter: ``a5.ports.EvidenceRetriever`` backed by A4's ``RetrievalService``."""

    def __init__(
        self,
        service: RetrievalServicePort,
        config: RetrievalConfig | None = None,
        *,
        tool_name: str = "a4_evidence_retrieval",
    ) -> None:
        if not callable(getattr(service, "search", None)):
            raise ValueError("service must provide a callable search method")
        if config is not None and not isinstance(config, RetrievalConfig):
            raise ValueError("config must be a RetrievalConfig or None")
        self._service = service
        self._config = config if config is not None else RetrievalConfig()
        self._tool_name = tool_name
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
            for chunk, score in self._selected_with_scores(result)
            if (record := self._to_evidence_record(chunk, score, result)) is not None
        ]
        diagnostics = self._build_diagnostics(question, plan, request, result, query)
        return RetrievalResult(
            evidence=evidence,
            tool_name=self._tool_name,
            diagnostics=diagnostics,
        )

    def _selected_with_scores(self, result: SearchResult) -> list[tuple[Any, float | None]]:
        """Selected chunks with their rerank score from the rank log (0..1)."""
        score_by_id: dict[str, float] = {}
        for log in result.rank_log:
            if log.candidate is None or log.candidate.chunk.chunk_id not in {
                chunk.chunk_id for chunk in result.selected_chunks
            }:
                continue
            score = log.candidate.rerank_score
            if score is not None:
                score_by_id[log.candidate.chunk.chunk_id] = max(0.0, min(1.0, float(score)))
        return [
            (chunk, score_by_id.get(chunk.chunk_id))
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
        score: float | None,
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
            },
            population=", ".join(chunk.pico_population) or None,
            intervention=", ".join(chunk.pico_intervention) or None,
            comparator=", ".join(chunk.pico_comparator) or None,
            outcome=", ".join(chunk.pico_outcome) or None,
            published_at=published_at,
            retrieval_score=score,
            evidence_level=chunk.evidence_level,
            spans=[],  # A3 Span Schema pending; never synthesized
            conflicts_with_ids=conflicts,
            mock=chunk.mock,
        )

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
            "run_hash": result.run_hash,
            "config_snapshot": self._config_snapshot(),
            "config_hash": self._config_hash(),
            "span_status": "UNKNOWN_A3_PENDING",
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
