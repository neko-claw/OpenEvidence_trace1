"""A4 native integration port.

This module defines only A4's *own* port surface.  It deliberately does NOT
redefine ``Question`` / ``SearchPlan`` / ``RetrievalRequest`` /
``RetrievalResult``: those are A5 public contracts owned by ``a5.domain.models``
(main repository).  A4 connects to A5 through the adapter in
``a5/adapters/a4_evidence_retriever.py``, which consumes the real A5 Pydantic
types and maps them onto A4's native models below.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .models import Candidate, EvidenceChunk, Query, SearchResult


@dataclass(frozen=True, slots=True)
class SupportGateResult:
    """A4 selection-filter result; never a medical verification verdict."""

    retained_chunk_ids: tuple[str, ...]
    reasons: tuple[str, ...] = ()


@runtime_checkable
class ClaimEvidenceSupportGate(Protocol):
    """P1/R3 selection filter supplied by A5 or an evaluation harness.

    The gate receives already selected candidates.  It may only retain IDs;
    it cannot add evidence outside the frozen candidate pool.
    """

    def filter(self, query: Query, candidates: Sequence[Candidate]) -> SupportGateResult: ...


@runtime_checkable
class CalibratedQualityScorer(Protocol):
    """Optional cross-query retrieval-quality evaluator for A5 Gate2.

    Scores must already be calibrated probabilities in [0, 1].  A4's RRF,
    feature, MMR, and Cross-Encoder scores implement ranking only and must
    never be substituted for this port.
    """

    def score(self, query: Query, chunks: Sequence[EvidenceChunk]) -> Mapping[str, float]: ...


@runtime_checkable
class RetrievalServicePort(Protocol):
    """A4's own retrieval contract (implemented by ``RetrievalService``)."""

    def search(self, query: Query) -> SearchResult:
        """Return one immutable retrieval result for ``query``."""
        ...


# Convenience mapping used by integration tests and the A5 adapter: A4 native
# result fields that the adapter must surface in ``RetrievalResult.diagnostics``.
DIAGNOSTIC_FIELDS = (
    "index_version",
    "corpus_version",
    "rerank_config_version",
    "status",
    "degradation_reasons",
    "degradation_codes",
    "retrieval_warning",
    "latency_ms",
    "stage_latency_ms",
    "run_hash",
    "reason_code_version",
    "condition",
    "initial_candidate_pool_hash",
    "stage_trace",
    "ranking_score_kind",
    "ranking_score_scope",
    "ranking_score_calibrated",
    "quality_scores",
    "quality_score_kind",
    "quality_score_scope",
    "quality_score_calibrated",
)
