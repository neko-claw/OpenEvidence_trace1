"""Contracts for the A4 clinical-evidence retrieval pipeline."""

from .adaptive import adapt_k
from .bge_m3 import BgeM3Embedder, BgeM3EmbeddingError
from .config import FeatureWeights, RetrievalConfig
from .config_io import ConfigYamlError, config_matches_yaml, load_config_yaml, write_config_yaml
from .cross_encoder import CrossEncoderError, CrossEncoderScorer
from .evaluation import (
    aggregate_chunk_qrels,
    claim_coverage_at_k,
    citation_coverage,
    citation_precision,
    duplicate_rate,
    evaluate_ranking,
    evaluate_span_ranking,
    hit_at_k,
    mrr,
    ndcg_at_k,
    recall_at_k,
    source_diversity,
    span_mrr,
    span_ndcg_at_k,
    span_recall_at_k,
    span_success_at_k,
    success_at_k,
    write_run_jsonl,
)
from .fusion import fuse_rrf
from .gate import SourceGateVerdict, check_source_gate
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
    "ConfigYamlError",
    "config_matches_yaml",
    "load_config_yaml",
    "write_config_yaml",
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
    "aggregate_chunk_qrels",
    "evaluate_span_ranking",
    "span_success_at_k",
    "span_recall_at_k",
    "span_mrr",
    "span_ndcg_at_k",
    "claim_coverage_at_k",
    "FeatureWeights",
    "FeatureReranker",
    "select_mmr",
    "fuse_rrf",
    "SourceGateVerdict",
    "check_source_gate",
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
