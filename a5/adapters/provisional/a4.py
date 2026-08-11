from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any

from a5.adapters.provisional.common import (
    UpstreamContractError,
    UpstreamRetrievalError,
    enum_text,
    fixture_like,
    join_terms,
    normalized_score,
    parse_datetime,
    positive_page,
    read_field,
    to_mapping,
)
from a5.domain.models import (
    EvidenceRecord,
    EvidenceSpan,
    Question,
    RetrievalRequest,
    RetrievalResult,
    SearchPlan,
)
from a5.domain.enums import RetrievalScoreKind, RetrievalScoreScope
from a5.adapters.provisional.a3 import A3SpanPayload
from a5.ports.a4_search_service import A4SearchService
from a5.runtime_config import IntegrationsConfig, load_runtime_config


A4QueryFactory = Callable[[dict[str, Any]], object]
A3SpanProvider = Callable[[str], Sequence[object]]


def provisional_query_factory(payload: dict[str, Any]) -> object:
    """Return a mapping for fakes; production injects A4's concrete Query factory."""
    return payload


class A4RAGRetriever:
    """Map A4 SearchResult to A5 without importing A4 concrete implementations."""

    def __init__(
        self,
        service: A4SearchService,
        *,
        query_factory: A4QueryFactory = provisional_query_factory,
        config: IntegrationsConfig | None = None,
        allow_mock: bool = False,
        span_provider: A3SpanProvider | None = None,
    ) -> None:
        self._service = service
        self._query_factory = query_factory
        self._config = config or load_runtime_config().integrations
        self._allow_mock = allow_mock
        self._span_provider = span_provider

    def retrieve(
        self,
        question: Question,
        plan: SearchPlan,
        request: RetrievalRequest,
    ) -> RetrievalResult:
        question_type = str(question.metadata.get("question_type", "general_evidence"))
        as_of_date = _as_of_date(question.metadata.get("as_of_date"))
        query_payload = {
            "query_id": f"{question.question_id}:tool-{request.tool_call_index}",
            "text": plan.queries[0],
            "language": _language(question.metadata.get("language")),
            "as_of_date": as_of_date,
            "question_type": self._config.a4_question_type_map.get(question_type, "generic"),
            "freshness": self._config.a4_freshness_map.get(question_type, "generic"),
            "topic": self._config.a4_topic_map.get(question_type, "generic"),
            "source_types": (
                self._config.a4_source_type_map.get(request.source_type, request.source_type),
            ),
            "domain": str(question.metadata.get("topic", "generic")),
            "pico_population": tuple(question.metadata.get("pico_population", ())),
            "pico_intervention": tuple(question.metadata.get("pico_intervention", ())),
            "pico_comparator": tuple(question.metadata.get("pico_comparator", ())),
            "pico_outcome": tuple(question.metadata.get("pico_outcome", ())),
            "atomic_claims": tuple(question.metadata.get("atomic_claims", ())),
        }
        result = self._service.search(self._query_factory(query_payload))
        required_result_fields = ("query_id", "index_version", "corpus_version", "rerank_config_version")
        missing_result_fields = [name for name in required_result_fields if not read_field(result, name)]
        if missing_result_fields:
            raise UpstreamContractError(
                "A4 SearchResult missing required version fields: " + ", ".join(missing_result_fields)
            )
        status = enum_text(read_field(result, "status", ""))
        if status not in {"ok", "partial", "empty", "failed"}:
            raise UpstreamRetrievalError("A4 SearchResult has an unknown status")
        if status == "failed":
            raise UpstreamRetrievalError("A4 retrieval failed")
        chunks = tuple(read_field(result, "selected_chunks", ()) or ())
        rank_logs = tuple(read_field(result, "rank_log", ()) or ())
        conflicts = tuple(read_field(result, "conflicts", ()) or ())
        scores, rank_diagnostics = _rank_diagnostics(rank_logs)
        self._enforce_experimental_capabilities(chunks, rank_diagnostics)
        evidence = self._map_chunks(chunks, scores, conflicts, result)
        return RetrievalResult(
            evidence=evidence,
            tool_name="a4_search",
            diagnostics={
                "adapter": type(self).__name__,
                "contract_version": self._config.a4.contract_version,
                "search_status": status,
                "index_version": read_field(result, "index_version"),
                "corpus_version": read_field(result, "corpus_version"),
                "rerank_config_version": read_field(result, "rerank_config_version"),
                "degradation_reasons": list(read_field(result, "degradation_reasons", ()) or ()),
                "retrieval_warning": read_field(result, "retrieval_warning"),
                "latency_ms": read_field(result, "latency_ms", 0),
                "stage_latency_ms": dict(read_field(result, "stage_latency_ms", {}) or {}),
                "rank_log": rank_diagnostics,
                "claim_support": _claim_support_diagnostics(read_field(result, "claim_support", ()) or ()),
                "claim_support_usage": "diagnostic_only_never_gate5",
                "score_semantics": {
                    "kind": RetrievalScoreKind.RANKING.value,
                    "scope": RetrievalScoreScope.QUERY_LOCAL.value,
                    "calibrated": False,
                    "gate2_eligible": False,
                },
                "span_status": (
                    "A3_SPANS_AVAILABLE"
                    if any(record.spans for record in evidence)
                    else "UNKNOWN_NO_A3_SPANS"
                ),
                "capabilities": {
                    "embedding": self._config.embedding_capability.model_dump(mode="json"),
                    "cross_encoder": self._config.cross_encoder_capability.model_dump(mode="json"),
                },
                "query_snapshot": {
                    "query_id": query_payload["query_id"],
                    "question_type": query_payload["question_type"],
                    "freshness": query_payload["freshness"],
                    "topic": query_payload["topic"],
                    "domain": query_payload["domain"],
                    "source_types": list(query_payload["source_types"]),
                    "as_of_date": as_of_date.isoformat(),
                },
            },
        )

    def _enforce_experimental_capabilities(
        self, chunks: tuple[object, ...], rank_diagnostics: list[dict[str, Any]]
    ) -> None:
        cross_encoder_keys = {"cross_encoder", "cross_encoder_score", "ce_score"}
        if not self._config.cross_encoder_capability.enabled and any(
            cross_encoder_keys.intersection(row.get("feature_scores", {}))
            for row in rank_diagnostics
        ):
            raise UpstreamContractError(
                "unapproved_cross_encoder: real dev ablation/calibration evidence is pending"
            )
        if not self._config.embedding_capability.enabled:
            for chunk in chunks:
                model = str(read_field(chunk, "embedding_model", "")).casefold()
                if not bool(read_field(chunk, "mock", False)) and model:
                    raise UpstreamContractError(
                        "unapproved_embedding_model: real dev Recall@50/latency validation is pending"
                    )

    def _map_chunks(
        self,
        chunks: tuple[object, ...],
        scores: dict[str, float | None],
        conflicts: tuple[object, ...],
        result: object,
    ) -> list[EvidenceRecord]:
        grouped: dict[str, list[object]] = defaultdict(list)
        for chunk in chunks:
            evidence_id = str(read_field(chunk, "evidence_id", "")).strip()
            if not evidence_id:
                raise UpstreamContractError("A4 selected chunk is missing evidence_id")
            grouped[evidence_id].append(chunk)
        conflict_map: dict[str, set[str]] = defaultdict(set)
        conflict_reasons: list[dict[str, str]] = []
        for conflict in conflicts:
            try:
                left, right, reason = conflict
            except (TypeError, ValueError) as error:
                raise UpstreamContractError("A4 conflict must be a three-item tuple") from error
            conflict_map[str(left)].add(str(right))
            conflict_map[str(right)].add(str(left))
            conflict_reasons.append({"left": str(left), "right": str(right), "reason": str(reason)})
        records: list[EvidenceRecord] = []
        for evidence_id, items in grouped.items():
            first = items[0]
            title = str(read_field(first, "title", "")).strip() or "Untitled upstream evidence"
            source_type = str(read_field(first, "source_type", "")).strip()
            stable_id = str(read_field(first, "stable_id", "")).strip()
            is_mock = bool(read_field(first, "mock", False))
            if fixture_like(evidence_id, stable_id, title) and not is_mock:
                raise UpstreamContractError("fixture-like A4 chunk must explicitly set mock=true")
            if is_mock and not self._allow_mock:
                raise UpstreamContractError("mock A4 chunks are disabled for this adapter")
            if not source_type or not stable_id or not title:
                raise UpstreamContractError(
                    "A4 selected chunk is missing source_type, stable_id, or title"
                )
            if not is_mock:
                required_provenance = {
                    "url": read_field(first, "url"),
                    "published_at": read_field(first, "published_at"),
                    "content_hash": read_field(first, "content_hash"),
                    "fetched_at": read_field(first, "fetched_at"),
                }
                missing = [name for name, value in required_provenance.items() if not value]
                if missing:
                    raise UpstreamContractError(
                        "Gate1 missing required A4 provenance: " + ", ".join(missing)
                    )
            spans: list[EvidenceSpan] = []
            texts: list[str] = []
            per_chunk: list[dict[str, Any]] = []
            for chunk in items:
                if str(read_field(chunk, "source_type", "")).strip() != source_type:
                    raise UpstreamContractError("A4 chunks for one evidence_id disagree on source_type")
                chunk_id = str(read_field(chunk, "chunk_id", "")).strip()
                text = str(read_field(chunk, "text", "")).strip()
                if not chunk_id or not text:
                    raise UpstreamContractError("A4 selected chunk is missing chunk_id/text")
                spans.extend(self._spans_for_chunk(chunk, evidence_id))
                texts.append(text)
                per_chunk.append(
                    {
                        "chunk_id": chunk_id,
                        "stable_id": str(read_field(chunk, "stable_id", "")),
                        "content_hash": str(read_field(chunk, "content_hash", "")),
                        "raw_page": read_field(chunk, "page"),
                        "retrieval_score": scores.get(chunk_id),
                    }
                )
            published_at = parse_datetime(read_field(first, "published_at"))
            records.append(
                EvidenceRecord(
                    id=evidence_id,
                    content="\n\n".join(texts),
                    source_type=source_type or "unknown",
                    title=title,
                    source_metadata={
                        "adapter": "A4RAGRetriever",
                        "contract_version": self._config.a4.contract_version,
                        "stable_id": stable_id or None,
                        "url": read_field(first, "url") or None,
                        "content_hash": read_field(first, "content_hash") or None,
                        "fetched_at": read_field(first, "fetched_at") or None,
                        "topic": read_field(first, "topic") or None,
                        "embedding_model": read_field(first, "embedding_model") or None,
                        "embedding_revision": read_field(first, "embedding_revision") or None,
                        "index_version": read_field(result, "index_version"),
                        "corpus_version": read_field(result, "corpus_version"),
                        "rerank_config_version": read_field(result, "rerank_config_version"),
                        "chunks": per_chunk,
                        "conflict_reasons": [
                            row for row in conflict_reasons if evidence_id in {row["left"], row["right"]}
                        ],
                        "source_integrity": (
                            "mock_fixture"
                            if is_mock
                            else "a4_a3_provenance_validated"
                        ),
                    },
                    population=join_terms(read_field(first, "pico_population", ())),
                    intervention=join_terms(read_field(first, "pico_intervention", ())),
                    comparator=join_terms(read_field(first, "pico_comparator", ())),
                    outcome=join_terms(read_field(first, "pico_outcome", ())),
                    published_at=published_at,
                    retrieval_score=max(
                        (score for chunk in items if (score := scores.get(str(read_field(chunk, "chunk_id", "")))) is not None),
                        default=None,
                    ),
                    retrieval_score_kind=RetrievalScoreKind.RANKING,
                    retrieval_score_scope=RetrievalScoreScope.QUERY_LOCAL,
                    retrieval_score_calibrated=False,
                    evidence_level=str(read_field(first, "evidence_level", "")).strip() or None,
                    spans=spans,
                    conflicts_with_ids=sorted(conflict_map[evidence_id]),
                    mock=is_mock,
                )
            )
        return records

    def _spans_for_chunk(self, chunk: object, evidence_id: str) -> list[EvidenceSpan]:
        if self._span_provider is None:
            return []
        chunk_id = str(read_field(chunk, "chunk_id", "")).strip()
        chunk_hash = str(read_field(chunk, "content_hash", "")).strip()
        evidence_hash = str(read_field(chunk, "evidence_content_hash", "")).strip()
        mapped: list[EvidenceSpan] = []
        for raw in self._span_provider(chunk_id) or ():
            span = A3SpanPayload.model_validate(to_mapping(raw))
            if span.evidence_id != evidence_id or span.chunk_id != chunk_id:
                raise UpstreamContractError(f"stale_span: {span.span_id}")
            if chunk_hash and span.chunk_content_hash != chunk_hash:
                raise UpstreamContractError(f"stale_span: chunk hash mismatch for {span.span_id}")
            if evidence_hash and span.evidence_content_hash != evidence_hash:
                raise UpstreamContractError(f"evidence_hash_mismatch: {span.span_id}")
            mapped.append(
                EvidenceSpan(
                    span_id=span.span_id,
                    chunk_id=span.chunk_id,
                    text=span.text,
                    page=span.page,
                    raw_page=span.raw_page,
                    section=span.section,
                    char_start=span.char_start,
                    char_end=span.char_end,
                    offset_scope=span.offset_scope,
                    document_char_start=span.document_char_start,
                    document_char_end=span.document_char_end,
                    span_content_hash=span.content_hash,
                    chunk_content_hash=span.chunk_content_hash,
                    evidence_content_hash=span.evidence_content_hash,
                )
            )
        return mapped


def _rank_diagnostics(rank_logs: tuple[object, ...]) -> tuple[dict[str, float | None], list[dict[str, Any]]]:
    scores: dict[str, float | None] = {}
    rows: list[dict[str, Any]] = []
    for log in rank_logs:
        candidate = read_field(log, "candidate")
        if candidate is None:
            continue
        chunk = read_field(candidate, "chunk")
        chunk_id = str(read_field(chunk, "chunk_id", "")).strip()
        if not chunk_id:
            continue
        score = normalized_score(read_field(candidate, "rerank_score"))
        scores[chunk_id] = score
        features = read_field(log, "feature_scores", {}) or read_field(candidate, "feature_scores", {}) or {}
        rows.append(
            {
                "chunk_id": chunk_id,
                "final_rank": read_field(log, "final_rank"),
                "selected": bool(read_field(log, "selected", False)),
                "rerank_score": score,
                "feature_scores": dict(features) if isinstance(features, Mapping) else {},
            }
        )
    return scores, rows


def _claim_support_diagnostics(items: object) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append(
            {
                "claim_index": read_field(item, "claim_index"),
                "decision": read_field(item, "decision"),
                "evidence_ids": list(read_field(item, "evidence_ids", ()) or ()),
                "reason": read_field(item, "reason", ""),
            }
        )
    return rows


def _as_of_date(value: object) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return date.today()


def _language(value: object) -> str:
    normalized = str(value or "zh").casefold()
    return "en" if normalized.startswith("en") else "zh"
