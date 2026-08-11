"""A4 native integration port.

This module defines only A4's *own* port surface.  It deliberately does NOT
redefine ``Question`` / ``SearchPlan`` / ``RetrievalRequest`` /
``RetrievalResult``: those are A5 public contracts owned by ``a5.domain.models``
(main repository).  A4 connects to A5 through the adapter in
``a5/adapters/a4_evidence_retriever.py``, which consumes the real A5 Pydantic
types and maps them onto A4's native models below.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from .models import EvidenceChunk, Query, RankLog, RetrievalAlignmentHint, SearchResult


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
)
