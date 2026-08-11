"""Deterministic offline metrics and JSONL audit records for A4 retrieval."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from math import isfinite, log2
from numbers import Real
from pathlib import Path
from types import MappingProxyType

from .bm25 import tokenize
from .models import Candidate, EvidenceChunk, RankLog, RetrievalAlignmentHint, ScoredChunk, SearchResult


def success_at_k(ranked_ids: Sequence[str], qrels: Mapping[str, float], k: int) -> float:
    """Return one when any positively relevant ID is present in the top ``k``."""
    ranked, relevance = _validate_ranking_and_qrels(ranked_ids, qrels, k)
    return float(any(relevance.get(item_id, 0.0) > 0.0 for item_id in ranked[:k]))


def hit_at_k(ranked_ids: Sequence[str], qrels: Mapping[str, float], k: int) -> float:
    """Return the binary hit/success indicator for the top ``k`` ranking."""
    return success_at_k(ranked_ids, qrels, k)


def recall_at_k(ranked_ids: Sequence[str], qrels: Mapping[str, float], k: int) -> float:
    """Return the fraction of positively relevant qrels retrieved in top ``k``."""
    ranked, relevance = _validate_ranking_and_qrels(ranked_ids, qrels, k)
    relevant_ids = {item_id for item_id, score in relevance.items() if score > 0.0}
    if not relevant_ids:
        return 0.0
    return len(relevant_ids.intersection(ranked[:k])) / len(relevant_ids)


def mrr(ranked_ids: Sequence[str], qrels: Mapping[str, float]) -> float:
    """Return reciprocal rank of the first positively relevant document."""
    ranked = _validate_ranked_ids(ranked_ids)
    relevance = _validate_qrels(qrels)
    for rank, item_id in enumerate(ranked, start=1):
        if relevance.get(item_id, 0.0) > 0.0:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked_ids: Sequence[str], qrels: Mapping[str, float], k: int) -> float:
    """Return linearly graded normalized DCG in ``[0, 1]`` at cutoff ``k``.

    Linear gain is intentional: it preserves arbitrary nonnegative qrel grades
    without risking overflow from an exponential gain transformation.
    """
    ranked, relevance = _validate_ranking_and_qrels(ranked_ids, qrels, k)
    ideal = sorted((score for score in relevance.values() if score > 0.0), reverse=True)[:k]
    if not ideal:
        return 0.0
    maximum_relevance = max(ideal)
    ideal_dcg = _dcg(ideal, maximum_relevance)
    if ideal_dcg == 0.0:
        return 0.0
    observed = [relevance.get(item_id, 0.0) for item_id in ranked[:k]]
    return min(1.0, max(0.0, _dcg(observed, maximum_relevance) / ideal_dcg))


def source_diversity(ranked_chunks: Sequence[EvidenceChunk]) -> float:
    """Return distinct normalized source types divided by returned chunks."""
    chunks = _validate_chunks(ranked_chunks)
    if not chunks:
        return 0.0
    return len({chunk.source_type.strip().casefold() for chunk in chunks}) / len(chunks)


def duplicate_rate(ranked_chunks: Sequence[EvidenceChunk]) -> float:
    """Return the proportion of chunks sharing a stable evidence identifier."""
    chunks = _validate_chunks(ranked_chunks)
    if not chunks:
        return 0.0
    return 1.0 - len({chunk.stable_id.strip().casefold() for chunk in chunks}) / len(chunks)


def evaluate_ranking(
    ranked_chunks_or_ids: Sequence[EvidenceChunk] | Sequence[str], qrels: Mapping[str, float], k: int
) -> Mapping[str, float]:
    """Calculate the frozen A4 retrieval metrics for one ranked result list.

    When chunks are supplied, diversity and document-duplicate metrics use all
    returned chunks (the final-context list), rather than the relevance cutoff.
    ID-only runs report these two provenance-dependent metrics as ``0.0``.
    """
    ranked_ids, chunks = _normalize_ranking_input(ranked_chunks_or_ids)
    metrics = {
        "success_at_k": success_at_k(ranked_ids, qrels, k),
        "recall_at_k": recall_at_k(ranked_ids, qrels, k),
        "mrr": mrr(ranked_ids, qrels),
        "ndcg_at_k": ndcg_at_k(ranked_ids, qrels, k),
        "hit_at_k": hit_at_k(ranked_ids, qrels, k),
        "source_diversity": source_diversity(chunks) if chunks is not None else 0.0,
        "duplicate_rate": duplicate_rate(chunks) if chunks is not None else 0.0,
    }
    if any(not isfinite(value) or not 0.0 <= value <= 1.0 for value in metrics.values()):
        raise ValueError("evaluation metrics must be finite values in [0, 1]")
    return MappingProxyType(metrics)


def citation_proxy_coverage(alignment_hints: Sequence[RetrievalAlignmentHint]) -> float:
    """Smoke proxy: share of claims with at least one alignment evidence id.

Token-overlap alignment hints are not A5 verification; this metric is a
pipeline smoke proxy only and must not be reported as citation quality."""
    supports = _validate_alignment_hints(alignment_hints)
    if not supports:
        return 0.0
    return sum(1 for support in supports if support.evidence_ids) / len(supports)


def claim_proxy_alignment_rate(alignment_hints: Sequence[RetrievalAlignmentHint]) -> float:
    """Smoke proxy: share of claims whose alignment verdict is ALIGNED."""
    supports = _validate_alignment_hints(alignment_hints)
    if not supports:
        return 0.0
    return sum(1 for support in supports if support.decision == "ALIGNED") / len(supports)


def citation_proxy_precision(alignment_hints: Sequence[RetrievalAlignmentHint]) -> float:
    """Smoke proxy: share of cited evidence ids that belong to an ALIGNED claim.

    Unlike ``citation_proxy_coverage`` (are claims cited?), this measures whether the
    cited evidence token-aligns with the adjacent claim.  It is NOT A5 citation
    precision: the final citation audit belongs to A5 (Gate5).
    """
    supports = _validate_alignment_hints(alignment_hints)
    total_citations = sum(len(support.evidence_ids) for support in supports)
    if total_citations == 0:
        return 0.0
    precise = sum(
        len(support.evidence_ids) for support in supports if support.decision == "ALIGNED"
    )
    return precise / total_citations


# --- 3.1 Qrel contract: atomic-point / evidence-span granularity -----------
# A span qrel maps one evidence span to the chunk that contains it, the atomic
# claim (``atomic_point_id``, may be empty for chunk-only qrels) it supports,
# and a nonnegative relevance grade.  Ranking is still over chunk IDs; a span
# is "retrieved" when its chunk is in the top ``k``.
SpanProxyQrel = tuple[str, str, float]  # (chunk_id, atomic_point_id, grade); chunk-level proxy until A3 spans arrive


def aggregate_chunk_qrels(span_qrels: Mapping[str, SpanProxyQrel]) -> Mapping[str, float]:
    """Collapse span-level qrels to chunk-level grades (max grade per chunk).

    Lets the standard ``evaluate_ranking`` metrics run on the same judgments.
    """
    normalized = _validate_span_qrels(span_qrels)
    grades: dict[str, float] = {}
    for _, (chunk_id, _, grade) in normalized.items():
        grades[chunk_id] = max(grades.get(chunk_id, 0.0), grade)
    return MappingProxyType(grades)


def span_proxy_success_at_k(ranked_ids: Sequence[str], span_qrels: Mapping[str, SpanProxyQrel], k: int) -> float:
    """One when any relevant span's chunk appears in the top ``k``."""
    ranked, spans = _validate_span_ranking(ranked_ids, span_qrels, k)
    positions = {chunk_id: position for position, chunk_id in enumerate(ranked, start=1)}
    return float(
        any(grade > 0.0 and positions.get(chunk_id, k + 1) <= k for chunk_id, _, grade in spans.values())
    )


def span_proxy_recall_at_k(ranked_ids: Sequence[str], span_qrels: Mapping[str, SpanProxyQrel], k: int) -> float:
    """Fraction of relevant evidence spans whose chunk is in the top ``k``."""
    ranked, spans = _validate_span_ranking(ranked_ids, span_qrels, k)
    relevant = [(chunk_id, grade) for chunk_id, _, grade in spans.values() if grade > 0.0]
    if not relevant:
        return 0.0
    top_k = set(ranked[:k])
    return sum(1 for chunk_id, _ in relevant if chunk_id in top_k) / len(relevant)


def span_proxy_mrr(ranked_ids: Sequence[str], span_qrels: Mapping[str, SpanProxyQrel]) -> float:
    """Reciprocal rank of the first relevant span's chunk."""
    ranked = _validate_ranked_ids(ranked_ids)
    spans = _validate_span_qrels(span_qrels)
    positions = {chunk_id: position for position, chunk_id in enumerate(ranked, start=1)}
    for chunk_id, _, grade in spans.values():
        if grade > 0.0 and chunk_id in positions:
            return 1.0 / positions[chunk_id]
    return 0.0


def span_proxy_ndcg_at_k(ranked_ids: Sequence[str], span_qrels: Mapping[str, SpanProxyQrel], k: int) -> float:
    """Linearly graded normalized DCG over evidence spans at cutoff ``k``.

    Spans sharing one chunk receive that chunk's rank, so a chunk with several
    supporting spans contributes proportionally more evidence without inflating
    the position.
    """
    ranked, spans = _validate_span_ranking(ranked_ids, span_qrels, k)
    positions = {chunk_id: position for position, chunk_id in enumerate(ranked, start=1)}
    relevant = [(chunk_id, grade) for chunk_id, _, grade in spans.values() if grade > 0.0]
    if not relevant:
        return 0.0
    maximum_relevance = max(grade for _, grade in relevant)
    ideal = sorted((grade for _, grade in relevant), reverse=True)[:k]
    ideal_dcg = _dcg(ideal, maximum_relevance)
    if ideal_dcg == 0.0:
        return 0.0
    observed = sorted(
        (position, grade)
        for chunk_id, grade in relevant
        if (position := positions.get(chunk_id, k + 1)) <= k
    )
    observed_dcg = _dcg([grade for _, grade in observed], maximum_relevance)
    return min(1.0, max(0.0, observed_dcg / ideal_dcg))


def claim_chunk_coverage_at_k(ranked_ids: Sequence[str], span_qrels: Mapping[str, SpanProxyQrel], k: int) -> float:
    """Fraction of atomic points with at least one retrieved relevant span.

    Atomic points without any positive span are ignored, so the metric answers
    "of the claims this question actually tests, how many are covered" (3.1
    Qrel 契约的 atomic_point_id 粒度).
    """
    ranked, spans = _validate_span_ranking(ranked_ids, span_qrels, k)
    points: dict[str, list[tuple[str, float]]] = {}
    for _, (chunk_id, point_id, grade) in spans.items():
        if not point_id or grade <= 0.0:
            continue
        points.setdefault(point_id, []).append((chunk_id, grade))
    if not points:
        return 0.0
    top_k = set(ranked[:k])
    covered = sum(1 for spans_of_point in points.values() if any(chunk_id in top_k for chunk_id, _ in spans_of_point))
    return covered / len(points)


def evaluate_span_proxy_metrics(ranked_ids: Sequence[str], span_qrels: Mapping[str, SpanProxyQrel], k: int) -> Mapping[str, float]:
    """Chunk-level span-proxy metrics; real span recall requires the A3 Span Schema (pending)."""
    metrics = {
        "span_proxy_success_at_k": span_proxy_success_at_k(ranked_ids, span_qrels, k),
        "span_proxy_recall_at_k": span_proxy_recall_at_k(ranked_ids, span_qrels, k),
        "span_proxy_mrr": span_proxy_mrr(ranked_ids, span_qrels),
        "span_proxy_ndcg_at_k": span_proxy_ndcg_at_k(ranked_ids, span_qrels, k),
        "claim_chunk_coverage_at_k": claim_chunk_coverage_at_k(ranked_ids, span_qrels, k),
    }
    if any(not isfinite(value) or not 0.0 <= value <= 1.0 for value in metrics.values()):
        raise ValueError("span evaluation metrics must be finite values in [0, 1]")
    return MappingProxyType(metrics)


def _validate_span_ranking(
    ranked_ids: Sequence[str], span_qrels: Mapping[str, SpanProxyQrel], k: int
) -> tuple[tuple[str, ...], dict[str, SpanProxyQrel]]:
    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError("k must be a positive integer")
    return _validate_ranked_ids(ranked_ids), _validate_span_qrels(span_qrels)


def _validate_span_qrels(span_qrels: Mapping[str, SpanProxyQrel]) -> dict[str, SpanProxyQrel]:
    if not isinstance(span_qrels, Mapping):
        raise ValueError("span_qrels must map span IDs to (chunk_id, atomic_point_id, grade) triples")
    normalized: dict[str, SpanProxyQrel] = {}
    for span_id, value in span_qrels.items():
        if not isinstance(span_id, str) or not span_id.strip():
            raise ValueError("span_qrels keys must be nonblank span IDs")
        if (
            not isinstance(value, tuple)
            or len(value) != 3
            or not isinstance(value[0], str)
            or not value[0].strip()
            or not isinstance(value[1], str)
            or not _finite_nonnegative(value[2])
        ):
            raise ValueError("span_qrels values must be (chunk_id, atomic_point_id, grade) triples")
        normalized[span_id] = (value[0], value[1], float(value[2]))
    return normalized


def conflict_rate(conflicts: Sequence[tuple[str, str, str]], chunk_count: int) -> float:
    """Conflicting evidence pairs over the maximum possible pair count."""
    if not isinstance(chunk_count, int) or isinstance(chunk_count, bool) or chunk_count < 0:
        raise ValueError("chunk_count must be a nonnegative integer")
    normalized = tuple(conflicts)
    if any(
        not isinstance(item, tuple) or len(item) != 3
        or any(not isinstance(part, str) or not part.strip() for part in item)
        for item in normalized
    ):
        raise ValueError("conflicts must be a sequence of (evidence_id, evidence_id, reason) triples")
    if chunk_count < 2:
        return 0.0
    return min(1.0, len(normalized) / (chunk_count * (chunk_count - 1) / 2))


def context_tokens(chunks: Sequence[EvidenceChunk]) -> int:
    """Estimated context tokens of the final evidence selection.

    Uses the annotated ``token_count`` when present (store populates it on
    upsert); otherwise estimates deterministically via the BM25 tokenizer.
    """
    validated = _validate_chunks(chunks) if chunks else ()
    total = 0
    for chunk in validated:
        if chunk.token_count > 0:
            total += chunk.token_count
        else:
            total += len(tokenize(f"{chunk.title} {chunk.text}"))
    return total


def estimated_cost(tokens: int, cost_per_1k_tokens: float = 0.002) -> float:
    """Rough USD estimate for context tokens at the configured rate."""
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
        raise ValueError("tokens must be a nonnegative integer")
    if not _finite_nonnegative(cost_per_1k_tokens):
        raise ValueError("cost_per_1k_tokens must be a finite nonnegative number")
    return tokens / 1000 * cost_per_1k_tokens


def _validate_alignment_hints(alignment_hints: Sequence[RetrievalAlignmentHint]) -> tuple[RetrievalAlignmentHint, ...]:
    if isinstance(alignment_hints, (str, bytes)) or not isinstance(alignment_hints, Sequence):
        raise ValueError("alignment_hints must be a sequence of RetrievalAlignmentHint")
    supports = tuple(alignment_hints)
    if any(not isinstance(support, RetrievalAlignmentHint) for support in supports):
        raise ValueError("alignment_hints must contain only RetrievalAlignmentHint values")
    return supports


def write_run_jsonl(path: str | Path, result: SearchResult) -> Path:
    """Append one JSON-only, query-safe A4 run record and return its path.

    The audit representation deliberately contains IDs, provenance, scores, and
    selection decisions, but not chunk text, query text, or exception objects.
    """
    if not isinstance(result, SearchResult):
        raise ValueError("result must be a SearchResult")
    destination = Path(path)
    _require_utf8_string(result.query_id, "SearchResult.query_id")
    record = {
        "query_id_hash": sha256(result.query_id.encode("utf-8")).hexdigest(),
        "index_version": result.index_version,
        "corpus_version": result.corpus_version,
        "rerank_config_version": result.rerank_config_version,
        "status": result.status.value,
        "degradation_reasons": list(result.degradation_reasons),
        "latency_ms": result.latency_ms,
        "timing_ms": dict(result.stage_latency_ms),
        "retrieval_warning": result.retrieval_warning,
        "selected_chunk_ids": [chunk.chunk_id for chunk in result.selected_chunks],
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
        "degradation_codes": list(result.degradation_codes),
        "run_hash": result.run_hash,
        "reason_code_version": result.reason_code_version,
        "conflicts": [list(conflict) for conflict in result.conflicts],
        "rank_log": [_rank_log_record(log) for log in result.rank_log],
    }
    _require_utf8_strings(record)
    try:
        line = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("SearchResult cannot be represented as strict JSON") from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8", newline="\n") as output:
        output.write(line + "\n")
    return destination


def _validate_ranking_and_qrels(
    ranked_ids: Sequence[str], qrels: Mapping[str, float], k: int
) -> tuple[tuple[str, ...], dict[str, float]]:
    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError("k must be a positive integer")
    return _validate_ranked_ids(ranked_ids), _validate_qrels(qrels)


def _validate_ranked_ids(ranked_ids: Sequence[str]) -> tuple[str, ...]:
    if isinstance(ranked_ids, (str, bytes)) or not isinstance(ranked_ids, Sequence):
        raise ValueError("ranked_ids must be a sequence of nonblank strings")
    ranked = tuple(ranked_ids)
    if any(not isinstance(item_id, str) or not item_id.strip() for item_id in ranked):
        raise ValueError("ranked_ids must contain only nonblank strings")
    if len(set(ranked)) != len(ranked):
        raise ValueError("ranked_ids must not contain duplicates")
    return ranked


def _validate_qrels(qrels: Mapping[str, float]) -> dict[str, float]:
    if not isinstance(qrels, Mapping):
        raise ValueError("qrels must be a mapping of IDs to nonnegative finite relevance")
    relevance: dict[str, float] = {}
    for item_id, score in qrels.items():
        if not isinstance(item_id, str) or not item_id.strip() or not _finite_nonnegative(score):
            raise ValueError("qrels must map nonblank IDs to nonnegative finite relevance")
        relevance[item_id] = float(score)
    return relevance


def _validate_chunks(ranked_chunks: Sequence[EvidenceChunk]) -> tuple[EvidenceChunk, ...]:
    if isinstance(ranked_chunks, (str, bytes)) or not isinstance(ranked_chunks, Sequence):
        raise ValueError("ranked_chunks must be a sequence of EvidenceChunk")
    chunks = tuple(ranked_chunks)
    if any(not isinstance(chunk, EvidenceChunk) for chunk in chunks):
        raise ValueError("ranked_chunks must contain only EvidenceChunk values")
    if any(
        not isinstance(value, str) or not value.strip()
        for chunk in chunks
        for value in (chunk.chunk_id, chunk.stable_id, chunk.source_type)
    ):
        raise ValueError("ranked_chunks require nonblank chunk_id, stable_id, and source_type")
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        raise ValueError("ranked_chunks must not contain duplicate chunk IDs")
    return chunks


def _normalize_ranking_input(
    ranked_chunks_or_ids: Sequence[EvidenceChunk] | Sequence[str],
) -> tuple[tuple[str, ...], tuple[EvidenceChunk, ...] | None]:
    if isinstance(ranked_chunks_or_ids, (str, bytes)) or not isinstance(ranked_chunks_or_ids, Sequence):
        raise ValueError("ranked_chunks_or_ids must be a sequence of IDs or EvidenceChunk values")
    values = tuple(ranked_chunks_or_ids)
    if not values:
        return (), None
    if all(isinstance(value, EvidenceChunk) for value in values):
        chunks = _validate_chunks(values)
        return tuple(chunk.chunk_id for chunk in chunks), chunks
    if all(isinstance(value, str) for value in values):
        return _validate_ranked_ids(values), None
    raise ValueError("ranked_chunks_or_ids must not mix IDs and EvidenceChunk values")


def _rank_log_record(log: RankLog) -> dict[str, object]:
    return {
        "candidate": _candidate_record(log.candidate) if log.candidate is not None else None,
        "bm25_candidates": [_scored_chunk_record(item) for item in log.bm25_candidates],
        "vector_candidates": [_scored_chunk_record(item) for item in log.vector_candidates],
        "fused_candidates": [_candidate_record(item) for item in log.fused_candidates],
        "reranked_candidates": [_candidate_record(item) for item in log.reranked_candidates],
        "selected_candidates": [_candidate_record(item) for item in log.selected_candidates],
        "feature_scores": dict(log.feature_scores),
        "final_rank": log.final_rank,
        "selected": log.selected,
        "rerank_config_version": log.rerank_config_version,
        "as_of_date": log.as_of_date.isoformat() if log.as_of_date is not None else None,
    }


def _scored_chunk_record(scored_chunk: ScoredChunk) -> dict[str, object]:
    return {
        "chunk": _chunk_record(scored_chunk.chunk),
        "score": scored_chunk.score,
        "rank": scored_chunk.rank,
        "stage": scored_chunk.stage,
        "feature_scores": dict(scored_chunk.feature_scores),
    }


def _candidate_record(candidate: Candidate) -> dict[str, object]:
    return {
        "chunk": _chunk_record(candidate.chunk),
        "chunk_id": candidate.chunk.chunk_id,
        "bm25_rank": candidate.bm25_rank,
        "vector_rank": candidate.vector_rank,
        "bm25_raw_score": candidate.bm25_raw_score,
        "vector_raw_score": candidate.vector_raw_score,
        "rrf_score": candidate.rrf_score,
        "rerank_score": candidate.rerank_score,
        "feature_scores": dict(candidate.feature_scores),
    }


def _chunk_record(chunk: EvidenceChunk) -> dict[str, object]:
    """Serialize reproducibility metadata without copying evidence or query text."""
    return {
        "chunk_id": chunk.chunk_id,
        "evidence_id": chunk.evidence_id,
        "stable_id": chunk.stable_id,
        "title": chunk.title,
        "source_type": chunk.source_type,
        "url": chunk.url,
        "published_at": chunk.published_at,
        "evidence_level": chunk.evidence_level,
        "pmid": chunk.pmid,
        "doi": chunk.doi,
        "nct_id": chunk.nct_id,
        "authors": list(chunk.authors),
        "guideline_name": chunk.guideline_name,
        "fetched_at": chunk.fetched_at,
        "pico_population": list(chunk.pico_population),
        "pico_intervention": list(chunk.pico_intervention),
        "pico_comparator": list(chunk.pico_comparator),
        "pico_outcome": list(chunk.pico_outcome),
        "is_tombstoned": chunk.is_tombstoned,
        "index_version": chunk.index_version,
        "corpus_version": chunk.corpus_version,
    }


def _require_utf8_strings(value: object) -> None:
    """Reject invalid Unicode from any contract field before opening the file."""
    if isinstance(value, str):
        _require_utf8_string(value, "SearchResult audit record")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _require_utf8_strings(key)
            _require_utf8_strings(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _require_utf8_strings(item)


def _require_utf8_string(value: str, field_name: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{field_name} must be UTF-8 encodable") from error


def _dcg(relevances: Sequence[float], maximum_relevance: float) -> float:
    """Compute a bounded, overflow-safe linear-gain DCG."""
    if maximum_relevance <= 0.0:
        return 0.0
    return sum((score / maximum_relevance) / log2(rank + 1) for rank, score in enumerate(relevances, start=1))


def _finite_nonnegative(value: object) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return isfinite(float(value)) and value >= 0
    except (OverflowError, TypeError, ValueError):
        return False
