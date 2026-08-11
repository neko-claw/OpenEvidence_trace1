"""Contracts for the A4 clinical-evidence retrieval pipeline."""

from .adaptive import adapt_k
from .bge_m3 import BgeM3Embedder, BgeM3EmbeddingError
from .config import FeatureWeights, RetrievalConfig
from .cross_encoder import CrossEncoderError, CrossEncoderScorer
from .evaluation import (
    citation_coverage,
    citation_precision,
    duplicate_rate,
    evaluate_ranking,
    hit_at_k,
    mrr,
    ndcg_at_k,
    recall_at_k,
    source_diversity,
    success_at_k,
    write_run_jsonl,
)
from .fusion import fuse_rrf
from .query_plan import QueryPlan, parse_query
from .rerank import FeatureReranker, select_mmr
from .service import RetrievalService
from .store import EvidenceStore, UpsertStats
from .support_check import ClaimSupport
from .ablation import AblationRow, decide, run_ablation, write_ablation_csv
from .tuning import (
    GridRow,
    QuestionRow,
    recall_curve,
    recall_curve_by_type,
    run_grid,
    grid_details,
    write_freeze_record,
    write_grid_details_csv,
    verify_frozen,
    require_frozen,
)
from .models import (
    Candidate,
    EvidenceChunk,
    Query,
    RankLog,
    ScoredChunk,
    SearchResult,
    SearchStatus,
)

__all__ = [
    "BgeM3Embedder",
    "BgeM3EmbeddingError",
    "Candidate",
    "ClaimSupport",
    "citation_coverage",
    "citation_precision",
    "CrossEncoderError",
    "CrossEncoderScorer",
    "adapt_k",
    "AblationRow",
    "decide",
    "run_ablation",
    "write_ablation_csv",
    "GridRow",
    "QuestionRow",
    "recall_curve",
    "recall_curve_by_type",
    "run_grid",
    "grid_details",
    "write_freeze_record",
    "write_grid_details_csv",
    "verify_frozen",
    "require_frozen",
    "EvidenceChunk",
    "duplicate_rate",
    "evaluate_ranking",
    "FeatureWeights",
    "FeatureReranker",
    "select_mmr",
    "fuse_rrf",
    "hit_at_k",
    "mrr",
    "ndcg_at_k",
    "Query",
    "QueryPlan",
    "parse_query",
    "RankLog",
    "RetrievalConfig",
    "RetrievalService",
    "EvidenceStore",
    "UpsertStats",
    "recall_at_k",
    "ScoredChunk",
    "SearchResult",
    "SearchStatus",
    "source_diversity",
    "success_at_k",
    "write_run_jsonl",
]
