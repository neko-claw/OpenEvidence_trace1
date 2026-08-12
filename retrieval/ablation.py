"""R0–R3 ablation runner and decision log (4.6)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
import json
from pathlib import Path
from statistics import mean

from .bm25 import BM25Index
from .config import RetrievalConfig
from .cross_encoder import CrossEncoderScorer
from .evaluation import (
    citation_proxy_coverage,
    citation_proxy_precision,
    claim_proxy_alignment_rate,
    conflict_rate,
    context_tokens,
    estimated_cost,
    evaluate_ranking,
)
from .models import EvidenceChunk, Query
from .models import InitialCandidatePool, RetrievalCondition
from .ports import SupportGateResult
from .service import RetrievalService
from .support_check import check_alignment, detect_conflicts
from .vector import InMemoryVectorSearch, VectorSearch

QueryVectors = Mapping[str, Sequence[float]]


@dataclass(frozen=True)
class AblationRow:
    condition: str  # R0 | R1 | R2 | R3
    recall_at_k0: float
    ndcg_at_k1: float
    mrr: float
    source_diversity: float
    duplicate_rate: float
    citation_proxy_precision: float
    citation_proxy_coverage: float
    claim_alignment_proxy_rate: float
    conflict_rate: float
    context_tokens: int
    estimated_cost_usd: float
    latency_ms: float
    initial_pool_hashes: tuple[str, ...] = ()
    stage_trace: tuple[str, ...] = ()


def run_ablation(
    questions: Sequence[tuple[Query, Mapping[str, float]]],
    chunks: Sequence[EvidenceChunk],
    *,
    query_vectors: QueryVectors | None = None,
    cross_encoder: CrossEncoderScorer | None = None,
    config: RetrievalConfig | None = None,
) -> list[AblationRow]:
    """Run R0 (RRF baseline), R1 (P0 main), R2 (+Cross-Encoder), R3 (+gate).

    Every condition consumes the same immutable initial candidate pool per
    question.  R3 uses an explicitly labelled token-overlap *proxy* gate for
    offline ablation only; it is not A5's medical support verifier.
    """
    if not questions:
        raise ValueError("questions must not be empty")
    base = config if config is not None else RetrievalConfig()
    rows: list[AblationRow] = []
    if cross_encoder is not None:
        r2_scorer = (
            cross_encoder
            if cross_encoder.alpha == base.cross_encoder_alpha
            else CrossEncoderScorer(
                model_name=cross_encoder.model_name,
                model_factory=cross_encoder.model_factory,
                alpha=base.cross_encoder_alpha,
                score_semantics=cross_encoder.score_semantics,
                score_transform=cross_encoder.score_transform,
            )
        )
    else:
        r2_scorer = None

    index = BM25Index(chunks)
    vector_search: VectorSearch | None = (
        InMemoryVectorSearch({chunk.chunk_id: (chunk, chunk.content_vector) for chunk in chunks if chunk.content_vector})
        if query_vectors is not None else None
    )

    def provider(query: Query) -> Sequence[float]:
        assert query_vectors is not None
        return query_vectors[query.query_id]

    service = RetrievalService(
        bm25_index=index,
        vector_search=vector_search,
        query_vector_provider=provider if query_vectors is not None else None,
        config=base,
        cross_encoder=r2_scorer,
        support_gate=_AlignmentProxyGate(base),
    )
    pools = {
        query.query_id: service.retrieve_initial_pool(query)
        for query, _qrels in questions
    }

    for condition in (RetrievalCondition.R0, RetrievalCondition.R1):
        collected = _run_condition(questions, service, pools, condition)
        rows.append(_aggregate(collected, condition.value))
    if r2_scorer is not None:
        for condition in (RetrievalCondition.R2, RetrievalCondition.R3):
            collected = _run_condition(questions, service, pools, condition)
            rows.append(_aggregate(collected, condition.value))

    return rows


def write_ablation_csv(path: str | Path, rows: Sequence[AblationRow]) -> Path:
    """Write the ablation table as CSV for reports."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "condition", "recall_at_k0", "ndcg_at_k1", "mrr", "source_diversity",
        "duplicate_rate", "citation_proxy_precision", "citation_proxy_coverage", "claim_alignment_proxy_rate",
        "conflict_rate", "context_tokens", "estimated_cost_usd", "latency_ms",
    )
    with destination.open("w", encoding="utf-8", newline="\n") as output:
        output.write(",".join(fields) + "\n")
        for row in rows:
            values = [str(getattr(row, field)) for field in fields]
            output.write(",".join(values) + "\n")
    return destination


def decide(rows: Sequence[AblationRow]) -> dict[str, str]:
    """Apply the 4.6 decision rules and return a machine-readable decision log."""
    by_condition = {row.condition: row for row in rows}
    decisions: dict[str, str] = {}
    r1 = by_condition.get("R1")
    r2 = by_condition.get("R2")
    r3 = by_condition.get("R3")
    if r1 is not None and r1.recall_at_k0 >= 0.85 and r1.claim_alignment_proxy_rate >= 0.5:
        decisions["cross_encoder"] = "not_required: R1 already meets recall and support targets"
    if r2 is not None and r1 is not None:
        if r2.ndcg_at_k1 > r1.ndcg_at_k1 and r2.claim_alignment_proxy_rate < r1.claim_alignment_proxy_rate:
            decisions["cross_encoder"] = "rejected: higher nDCG but lower claim support rate"
        elif r2.ndcg_at_k1 <= r1.ndcg_at_k1:
            decisions["cross_encoder"] = "rejected: no nDCG gain over R1"
        else:
            decisions["cross_encoder"] = "accepted: nDCG gain without support loss"
    if r3 is not None and r1 is not None:
        if r3.claim_alignment_proxy_rate >= r1.claim_alignment_proxy_rate and r3.conflict_rate <= r1.conflict_rate:
            decisions["gate"] = "accepted: gate improves or preserves support without more conflicts"
        else:
            decisions["gate"] = "review: gate changed support/conflict balance; inspect per-question rows"
    return decisions


def _run_condition(
    questions: Sequence[tuple[Query, Mapping[str, float]]],
    service: RetrievalService,
    pools: Mapping[str, InitialCandidatePool],
    condition: RetrievalCondition,
) -> list[tuple[Query, Mapping[str, float], object]]:
    """Return (query, qrels, per-question summary) triples for one condition."""
    collected: list[tuple[Query, Mapping[str, float], object]] = []
    for query, qrels in questions:
        result = service.search_from_pool(query, pools[query.query_id], condition)
        selected = list(result.selected_chunks)
        summary = {
            "selected": selected,
            "qrels": qrels,
            "alignment_hints": result.alignment_hints,
            "conflicts": detect_conflicts(selected),
            "latency_ms": result.latency_ms,
            "pool_hash": result.initial_candidate_pool_hash,
            "stage_trace": result.stage_trace,
            "reranked_ids": [
                log.candidate.chunk.chunk_id for log in result.rank_log if log.candidate is not None
            ],
        }
        collected.append((query, qrels, summary))
    return collected


def _aggregate(collected: Sequence[tuple[Query, Mapping[str, float], object]], condition: str) -> AblationRow:
    recalls: list[float] = []
    ndcgs: list[float] = []
    mrrs: list[float] = []
    diversities: list[float] = []
    duplicates: list[float] = []
    latencies: list[float] = []
    total_tokens = 0
    total_cost = 0.0
    precision_scores: list[float] = []
    citation_scores: list[float] = []
    support_scores: list[float] = []
    conflict_scores: list[float] = []
    for query, qrels, summary in collected:
        data = summary
        selected = data["selected"]
        ranked_ids = [chunk.chunk_id for chunk in selected]
        metrics = evaluate_ranking(ranked_ids, qrels, 6)
        recalls.append(float(metrics["recall_at_k"]))
        ndcgs.append(float(metrics["ndcg_at_k"]))
        mrrs.append(float(metrics["mrr"]))
        diversities.append(float(metrics["source_diversity"]))
        duplicates.append(float(metrics["duplicate_rate"]))
        latencies.append(float(data["latency_ms"]))
        total_tokens += context_tokens(selected)
        total_cost += estimated_cost(context_tokens(selected))
        if data["alignment_hints"]:
            precision_scores.append(citation_proxy_precision(data["alignment_hints"]))
            citation_scores.append(citation_proxy_coverage(data["alignment_hints"]))
            support_scores.append(claim_proxy_alignment_rate(data["alignment_hints"]))
        conflict_scores.append(conflict_rate(data["conflicts"], len(selected)))
    return AblationRow(
        condition=condition,
        recall_at_k0=mean(recalls) if recalls else 0.0,
        ndcg_at_k1=mean(ndcgs) if ndcgs else 0.0,
        mrr=mean(mrrs) if mrrs else 0.0,
        source_diversity=mean(diversities) if diversities else 0.0,
        duplicate_rate=mean(duplicates) if duplicates else 0.0,
        citation_proxy_precision=mean(precision_scores) if precision_scores else 0.0,
        citation_proxy_coverage=mean(citation_scores) if citation_scores else 0.0,
        claim_alignment_proxy_rate=mean(support_scores) if support_scores else 0.0,
        conflict_rate=mean(conflict_scores) if conflict_scores else 0.0,
        context_tokens=total_tokens,
        estimated_cost_usd=round(total_cost, 6),
        latency_ms=mean(latencies) if latencies else 0.0,
        initial_pool_hashes=tuple(data["pool_hash"] for _, _, data in collected),
        stage_trace=tuple(dict.fromkeys(stage for _, _, data in collected for stage in data["stage_trace"])),
    )


class _AlignmentProxyGate:
    """Offline R3 proxy; A5 Gate5 remains the publication authority."""

    def __init__(self, config: RetrievalConfig) -> None:
        self._config = config

    def filter(self, query: Query, candidates: Sequence[object]) -> SupportGateResult:
        chunks = [candidate.chunk for candidate in candidates]
        if not query.atomic_claims:
            return SupportGateResult((), ("r3_proxy_no_atomic_claims",))
        hints = check_alignment(query, query.atomic_claims, chunks, self._config)
        aligned_evidence_ids = {
            evidence_id
            for hint in hints
            if hint.decision == "ALIGNED"
            for evidence_id in hint.evidence_ids
        }
        retained = tuple(
            chunk.chunk_id for chunk in chunks if chunk.evidence_id in aligned_evidence_ids
        )
        reasons = () if retained else ("r3_proxy_removed_all_unsupported_candidates",)
        return SupportGateResult(retained, reasons)
