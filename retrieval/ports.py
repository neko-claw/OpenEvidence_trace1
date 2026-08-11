"""Canonical A5/A6 integration ports for the A4 retrieval module.

These port types implement the documented ``a5.ports.EvidenceRetriever``
contract (Question / SearchPlan / RetrievalRequest -> RetrievalResult) that the
main repository expects.  They live here so the A4 branch stays self-contained
and testable; when merged into the main ``openevidence-mvp`` project, ``a5``
may re-export or wrap them (see ``a5/retrieval_bridge.py``).

Boundary rules encoded in the ports:

- ``RetrievalResult`` exposes **only** ``selected_chunks`` (plus the audit
  trail); A5 must generate and audit citations from exactly these chunks.
- ``out_of_scope`` requests never return chunks: the adapter returns an empty
  result with an explicit reason, and final scope refusal belongs to A1/A5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from .models import ClaimSupport, EvidenceChunk, Query, RankLog


@dataclass(frozen=True, slots=True)
class Question:
    """A normalized question as A5 submits it to the retriever."""

    question_id: str
    text: str
    language: str = "zh"
    as_of_date: date | None = None
    pico_population: tuple[str, ...] = ()
    pico_intervention: tuple[str, ...] = ()
    pico_comparator: tuple[str, ...] = ()
    pico_outcome: tuple[str, ...] = ()
    atomic_claims: tuple[str, ...] = ()
    english_terms: tuple[str, ...] = ()
    out_of_scope: bool = False


@dataclass(frozen=True, slots=True)
class SearchPlan:
    """Constraints for one retrieval request (question_type / freshness / K)."""

    topic: str = "generic"
    question_type: str = "generic"
    freshness: str = "generic"
    domain: str = "generic"
    source_types: tuple[str, ...] = ()
    evidence_levels: tuple[str, ...] = ()
    index_version: str | None = None
    rerank_config_version: str | None = None
    max_chunks: int | None = None


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    """One retrieval call: a question plus an optional plan."""

    question: Question
    plan: SearchPlan | None = None


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """The A5 hand-off payload: selected evidence plus the full audit trail.

    ``status`` is one of ``ok`` / ``partial`` / ``empty`` / ``failed`` and is
    never silently upgraded.  A5 must answer using ``selected_chunks`` only.
    """

    question_id: str
    status: str
    selected_chunks: tuple[EvidenceChunk, ...] = ()
    rank_log: tuple[RankLog, ...] = ()
    degradation_reasons: tuple[str, ...] = ()
    retrieval_warning: str | None = None
    claim_support: tuple[ClaimSupport, ...] = ()
    index_version: str = ""
    rerank_config_version: str = ""
    latency_ms: float = 0.0
    out_of_scope: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.question_id, str) or not self.question_id.strip():
            raise ValueError("question_id must be a nonblank string")
        if self.status not in {"ok", "partial", "empty", "failed"}:
            raise ValueError("status must be one of ok/partial/empty/failed")
        if not isinstance(self.out_of_scope, bool):
            raise ValueError("out_of_scope must be a bool")


class EvidenceRetriever(Protocol):
    """The port A5 consumes (a5.ports.EvidenceRetriever)."""

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """Return the evidence selection for one question, never fabricated IDs."""


def question_to_query(question: Question, plan: SearchPlan | None = None) -> Query:
    """Build the immutable A4 ``Query`` from the port types."""
    return Query(
        query_id=question.question_id,
        text=question.text,
        language=question.language,
        pico_population=question.pico_population,
        pico_intervention=question.pico_intervention,
        pico_comparator=question.pico_comparator,
        pico_outcome=question.pico_outcome,
        as_of_date=question.as_of_date or date(2026, 8, 11),
        topic=plan.topic if plan is not None else "generic",
        question_type=plan.question_type if plan is not None else "generic",
        freshness=plan.freshness if plan is not None else "generic",
        english_terms=question.english_terms,
        source_types=plan.source_types if plan is not None else (),
        evidence_levels=plan.evidence_levels if plan is not None else (),
        atomic_claims=question.atomic_claims,
        domain=plan.domain if plan is not None else "generic",
        out_of_scope=question.out_of_scope,
    )


def result_to_retrieval_result(query: Query, result) -> RetrievalResult:
    """Map an A4 ``SearchResult`` onto the port payload."""
    from .models import SearchResult, SearchStatus

    if not isinstance(result, SearchResult):
        raise ValueError("result must be a SearchResult")
    return RetrievalResult(
        question_id=query.query_id,
        status=result.status.value,
        selected_chunks=tuple(result.selected_chunks),
        rank_log=tuple(result.rank_log),
        degradation_reasons=tuple(result.degradation_reasons),
        retrieval_warning=result.retrieval_warning,
        claim_support=tuple(result.claim_support),
        index_version=result.index_version,
        rerank_config_version=result.rerank_config_version,
        latency_ms=result.latency_ms,
        out_of_scope=query.out_of_scope,
    )
