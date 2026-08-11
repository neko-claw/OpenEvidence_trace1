"""K-grid tuning, recall curves, and configuration freeze records (4.3).

The runner is a dev-time tool: it sweeps ``(k0, k1, k2)`` over a question set
with qrels, aggregates metrics per configuration, and can write a freeze
record so formal runs can be verified against the frozen configuration.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean

from .bm25 import BM25Index
from .config import RetrievalConfig
from .evaluation import evaluate_ranking
from .models import EvidenceChunk, Query
from .service import RetrievalService
from .vector import InMemoryVectorSearch, VectorSearch

QueryVectors = Mapping[str, Sequence[float]]


@dataclass(frozen=True)
class GridRow:
    k0: int
    k1: int
    k2: int
    success_at_k0: float
    recall_at_k0: float
    ndcg_at_k2: float
    mrr: float
    hit_at_k2: float
    latency_ms: float


@dataclass(frozen=True)
class QuestionRow:
    """Per-question metrics for one configuration (4.3.3 逐题结果)."""

    k0: int
    k1: int
    k2: int
    question_id: str
    question_type: str
    success_at_k0: float
    recall_at_k0: float
    ndcg_at_k2: float
    mrr: float
    hit_at_k2: float
    latency_ms: float


def run_grid(
    questions: Sequence[tuple[Query, Mapping[str, float]]],
    chunks: Sequence[EvidenceChunk],
    *,
    k0_values: Sequence[int] = (20, 50, 80, 100, 150),
    k1_values: Sequence[int] = (10, 20, 30, 50),
    k2_values: Sequence[int] = (3, 5, 8, 10),
    query_vectors: QueryVectors | None = None,
    config: RetrievalConfig | None = None,
) -> list[GridRow]:
    """Sweep K triples over dev questions and return aggregated rows.

    ``query_vectors`` maps ``query_id`` to a fixed embedding (or ``None`` to
    run BM25-only).  The returned rows are ordered by (k0, k1, k2).
    """
    if not questions:
        raise ValueError("questions must not be empty")
    if not isinstance(chunks, Sequence) or any(not isinstance(chunk, EvidenceChunk) for chunk in chunks):
        raise ValueError("chunks must be a sequence of EvidenceChunk")
    base_config = config if config is not None else RetrievalConfig()
    rows: list[GridRow] = []
    for k0 in k0_values:
        for k1 in k1_values:
            for k2 in k2_values:
                if k2 > k1:
                    continue
                cfg = replace(
                    base_config,
                    fusion_top_k=k0,
                    rerank_top_k=k1,
                    selection_top_k=k2,
                )
                rows.append(_evaluate_config(questions, chunks, cfg, query_vectors))
    return rows


def grid_details(
    questions: Sequence[tuple[Query, Mapping[str, float]]],
    chunks: Sequence[EvidenceChunk],
    *,
    k0_values: Sequence[int] = (20, 50, 80, 100, 150),
    k1_values: Sequence[int] = (10, 20, 30, 50),
    k2_values: Sequence[int] = (3, 5, 8, 10),
    query_vectors: QueryVectors | None = None,
    config: RetrievalConfig | None = None,
) -> list[QuestionRow]:
    """Sweep K triples and return one row per (configuration, question).

    This is the 逐题明细 required by 4.3.3: report per-question results and
    per-type curves instead of a single averaged ``Recall@50``.
    """
    if not questions:
        raise ValueError("questions must not be empty")
    if not isinstance(chunks, Sequence) or any(not isinstance(chunk, EvidenceChunk) for chunk in chunks):
        raise ValueError("chunks must be a sequence of EvidenceChunk")
    base_config = config if config is not None else RetrievalConfig()
    details: list[QuestionRow] = []
    for k0 in k0_values:
        for k1 in k1_values:
            for k2 in k2_values:
                if k2 > k1:
                    continue
                cfg = replace(
                    base_config,
                    fusion_top_k=k0,
                    rerank_top_k=k1,
                    selection_top_k=k2,
                )
                details.extend(_evaluate_questions(questions, chunks, cfg, query_vectors))
    return details


def write_grid_details_csv(path: str | Path, details: Sequence[QuestionRow]) -> Path:
    """Write per-question tuning detail rows as CSV."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "k0", "k1", "k2", "question_id", "question_type",
        "success_at_k0", "recall_at_k0", "ndcg_at_k2", "mrr", "hit_at_k2", "latency_ms",
    )
    with destination.open("w", encoding="utf-8", newline="\n") as output:
        output.write(",".join(fields) + "\n")
        for row in details:
            output.write(",".join(str(getattr(row, field)) for field in fields) + "\n")
    return destination


def recall_curve_by_type(
    questions: Sequence[tuple[Query, Mapping[str, float]]],
    chunks: Sequence[EvidenceChunk],
    *,
    k0_values: Sequence[int] = (20, 50, 80, 100, 150),
    k1: int = 25,
    k2: int = 6,
    query_vectors: QueryVectors | None = None,
    config: RetrievalConfig | None = None,
) -> dict[str, list[GridRow]]:
    """Recall curve per question type (4.3.3 按题型的召回曲线)."""
    by_type: dict[str, list[tuple[Query, Mapping[str, float]]]] = {}
    for query, qrels in questions:
        by_type.setdefault(query.question_type, []).append((query, qrels))
    return {
        question_type: run_grid(
            grouped,
            chunks,
            k0_values=k0_values,
            k1_values=(k1,),
            k2_values=(k2,),
            query_vectors=query_vectors,
            config=config,
        )
        for question_type, grouped in sorted(by_type.items())
    }


def recall_curve(
    questions: Sequence[tuple[Query, Mapping[str, float]]],
    chunks: Sequence[EvidenceChunk],
    *,
    k0_values: Sequence[int] = (20, 50, 80, 100, 150),
    k1: int = 25,
    k2: int = 6,
    query_vectors: QueryVectors | None = None,
    config: RetrievalConfig | None = None,
) -> list[GridRow]:
    """Recall-focused curve over K0 with K1/K2 fixed (pick the knee)."""
    return run_grid(
        questions,
        chunks,
        k0_values=k0_values,
        k1_values=(k1,),
        k2_values=(k2,),
        query_vectors=query_vectors,
        config=config,
    )


def write_freeze_record(
    path: str | Path,
    *,
    chosen: GridRow,
    config: RetrievalConfig,
    dev_summary: Mapping[str, float],
    note: str = "",
) -> Path:
    """Write an immutable freeze record for the chosen K triple."""
    record = {
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chosen_k": {"k0": chosen.k0, "k1": chosen.k1, "k2": chosen.k2},
        "config": {
            "rerank_config_version": config.rerank_config_version,
            "index_version": config.index_version,
            "corpus_version": config.corpus_version,
            "weights": {
                "semantic": config.feature_weights.semantic,
                "lexical": config.feature_weights.lexical,
                "pico_match": config.feature_weights.pico_match,
                "evidence_level": config.feature_weights.evidence_level,
                "freshness": config.feature_weights.freshness,
                "source_reliability": config.feature_weights.source_reliability,
            },
            "mmr_lambda": config.mmr_lambda,
            "cross_encoder_alpha": config.cross_encoder_alpha,
            "freshness_weight_latest_trial": config.freshness_weight_latest_trial,
        },
        "dev_metrics": dict(dev_summary),
        "note": note,
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def verify_frozen(freeze_path: str | Path, config: RetrievalConfig) -> bool:
    """Return whether ``config`` exactly matches the frozen record.

    Compares K limits, weights, MMR/redundancy parameters, alpha, freshness
    weight, and all version strings; any drift means the config is not frozen.
    """
    try:
        record = json.loads(Path(freeze_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    chosen = record.get("chosen_k")
    recorded = record.get("config", {})
    if not isinstance(chosen, dict) or not isinstance(recorded, dict):
        return False
    if not isinstance(config, RetrievalConfig):
        return False
    weights = recorded.get("weights", {})
    return (
        chosen.get("k0") == config.fusion_top_k
        and chosen.get("k1") == config.rerank_top_k
        and chosen.get("k2") == config.selection_top_k
        and recorded.get("rerank_config_version") == config.rerank_config_version
        and recorded.get("index_version") == config.index_version
        and recorded.get("corpus_version") == config.corpus_version
        and weights.get("semantic") == config.feature_weights.semantic
        and weights.get("lexical") == config.feature_weights.lexical
        and weights.get("pico_match") == config.feature_weights.pico_match
        and weights.get("evidence_level") == config.feature_weights.evidence_level
        and weights.get("freshness") == config.feature_weights.freshness
        and weights.get("source_reliability") == config.feature_weights.source_reliability
        and recorded.get("mmr_lambda") == config.mmr_lambda
        and recorded.get("cross_encoder_alpha") == config.cross_encoder_alpha
        and recorded.get("freshness_weight_latest_trial") == config.freshness_weight_latest_trial
    )


def require_frozen(freeze_path: str | Path, config: RetrievalConfig) -> None:
    """Fail closed unless the config exactly matches the freeze record.

    Call before running formal questions: after the freeze point, no weight,
    K value, alpha, or version may drift (4.3.3 不再根据正式题回退调参).
    """
    if not verify_frozen(freeze_path, config):
        raise ValueError(
            f"config is not frozen: {config.rerank_config_version} does not match "
            f"{Path(freeze_path).name}; refuse to run formal questions"
        )


def _evaluate_config(
    questions: Sequence[tuple[Query, Mapping[str, float]]],
    chunks: Sequence[EvidenceChunk],
    config: RetrievalConfig,
    query_vectors: QueryVectors | None,
) -> GridRow:
    question_rows = _evaluate_questions(questions, chunks, config, query_vectors)
    return GridRow(
        k0=config.fusion_top_k,
        k1=config.rerank_top_k,
        k2=config.selection_top_k,
        success_at_k0=mean(row.success_at_k0 for row in question_rows) if question_rows else 0.0,
        recall_at_k0=mean(row.recall_at_k0 for row in question_rows) if question_rows else 0.0,
        ndcg_at_k2=mean(row.ndcg_at_k2 for row in question_rows) if question_rows else 0.0,
        mrr=mean(row.mrr for row in question_rows) if question_rows else 0.0,
        hit_at_k2=mean(row.hit_at_k2 for row in question_rows) if question_rows else 0.0,
        latency_ms=mean(row.latency_ms for row in question_rows) if question_rows else 0.0,
    )


def _evaluate_questions(
    questions: Sequence[tuple[Query, Mapping[str, float]]],
    chunks: Sequence[EvidenceChunk],
    config: RetrievalConfig,
    query_vectors: QueryVectors | None,
) -> list[QuestionRow]:
    index = BM25Index(chunks)
    vector_search: VectorSearch | None = (
        InMemoryVectorSearch({chunk.chunk_id: (chunk, chunk.content_vector) for chunk in chunks if chunk.content_vector})
        if query_vectors is not None
        else None
    )

    def provider(query: Query) -> Sequence[float]:
        assert query_vectors is not None
        return query_vectors[query.query_id]

    service = RetrievalService(
        bm25_index=index,
        vector_search=vector_search,
        query_vector_provider=provider if query_vectors is not None else None,
        config=config,
    )

    rows: list[QuestionRow] = []
    for query, qrels in questions:
        result = service.search(query)
        ranked_ids = [chunk.chunk_id for chunk in result.selected_chunks]
        metrics = evaluate_ranking(ranked_ids, qrels, config.selection_top_k)
        rows.append(
            QuestionRow(
                k0=config.fusion_top_k,
                k1=config.rerank_top_k,
                k2=config.selection_top_k,
                question_id=query.query_id,
                question_type=query.question_type,
                success_at_k0=float(metrics["success_at_k"]),
                recall_at_k0=float(metrics["recall_at_k"]),
                ndcg_at_k2=float(metrics["ndcg_at_k"]),
                mrr=float(metrics["mrr"]),
                hit_at_k2=float(metrics["hit_at_k"]),
                latency_ms=result.latency_ms,
            )
        )
    return rows
