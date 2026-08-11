"""Validated, versioned configuration for the A4 P0 retrieval pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose, isfinite

from .models import MAX_RRF_OPERAND


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_positive_rrf_operand(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0 or value > MAX_RRF_OPERAND:
        raise ValueError(f"{field_name} must be a positive integer within the float-representable domain")


def _require_nonblank(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a nonblank string")


def _is_float_representable_finite(value: object) -> bool:
    """Avoid leaking OverflowError from public frozen-object mutation."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class FeatureWeights:
    """Normalized P0 reranking weights; each value is independently auditable."""

    semantic: float = 0.30
    lexical: float = 0.20
    pico_match: float = 0.15
    evidence_level: float = 0.15
    freshness: float = 0.10
    source_reliability: float = 0.10

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Recheck the invariant when a config consumes these weights."""
        weights = (
            self.semantic,
            self.lexical,
            self.pico_match,
            self.evidence_level,
            self.freshness,
            self.source_reliability,
        )
        if any(
            not _is_float_representable_finite(weight)
            or weight < 0
            for weight in weights
        ):
            raise ValueError("feature weights must be finite nonnegative numbers")
        if not isclose(sum(weights), 1.0, abs_tol=1e-6):
            raise ValueError("feature weights must sum to one")


@dataclass(frozen=True, slots=True)
class RetrievalConfig:
    """P0 limits and weight configuration for one reproducible retrieval release."""

    bm25_top_k: int = 50
    vector_top_k: int = 50
    fusion_top_k: int = 80
    rerank_top_k: int = 25
    selection_top_k: int = 6
    rrf_k: int = 60
    max_chunks_per_document: int = 2
    max_chunks_per_source: int = 4
    mmr_lambda: float = 0.75
    evidence_type_bonus: float = 0.03
    redundancy_penalty: float = 0.15
    cross_encoder_alpha: float = 0.5
    freshness_weight_latest_trial: float = 0.20
    source_quality_table: tuple[tuple[str, float], ...] = (
        ("guideline", 1.0),
        ("pubmed", 0.9),
        ("trials", 0.85),
        ("europepmc", 0.8),
    )
    latest_window_days: int = 1826
    feature_weights: FeatureWeights = field(default_factory=FeatureWeights)
    index_version: str = "v1"
    corpus_version: str = "v1"
    rerank_config_version: str = "p0-v1"

    def __post_init__(self) -> None:
        for field_name in (
            "bm25_top_k",
            "vector_top_k",
            "fusion_top_k",
            "rerank_top_k",
            "selection_top_k",
            "max_chunks_per_document",
            "max_chunks_per_source",
            "latest_window_days",
        ):
            _require_positive_int(getattr(self, field_name), field_name)
        _require_positive_rrf_operand(self.rrf_k, "rrf_k")
        if not _is_float_representable_finite(self.mmr_lambda) or not 0 <= self.mmr_lambda <= 1:
            raise ValueError("mmr_lambda must be a finite number in [0, 1]")
        if not _is_float_representable_finite(self.evidence_type_bonus) or self.evidence_type_bonus < 0:
            raise ValueError("evidence_type_bonus must be a finite nonnegative number")
        if not _is_float_representable_finite(self.redundancy_penalty) or self.redundancy_penalty < 0:
            raise ValueError("redundancy_penalty must be a finite nonnegative number")
        if not _is_float_representable_finite(self.cross_encoder_alpha) or not 0 <= self.cross_encoder_alpha <= 1:
            raise ValueError("cross_encoder_alpha must be a finite number in [0, 1]")
        if not _is_float_representable_finite(self.freshness_weight_latest_trial) or self.freshness_weight_latest_trial < 0:
            raise ValueError("freshness_weight_latest_trial must be a finite nonnegative number")
        if not isinstance(self.source_quality_table, tuple) or any(
            not isinstance(pair, tuple) or len(pair) != 2
            or not isinstance(pair[0], str) or not pair[0].strip()
            or not _is_float_representable_finite(pair[1]) or pair[1] < 0
            for pair in self.source_quality_table
        ):
            raise ValueError("source_quality_table must be a tuple of (source_type, score) pairs")
        if not isinstance(self.feature_weights, FeatureWeights):
            raise ValueError("feature_weights must be a FeatureWeights instance")
        self.feature_weights.validate()
        for field_name in ("index_version", "corpus_version", "rerank_config_version"):
            _require_nonblank(getattr(self, field_name), field_name)
