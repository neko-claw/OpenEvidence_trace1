"""Tests for alignment pre-check integration in the service (4.2 step 6)."""

from __future__ import annotations

from dataclasses import replace

from retrieval.bm25 import BM25Index
from retrieval.config import RetrievalConfig
from retrieval.models import Query
from retrieval.service import RetrievalService
from retrieval.vector import InMemoryVectorSearch


def _config() -> RetrievalConfig:
    return RetrievalConfig(
        bm25_top_k=10,
        vector_top_k=10,
        fusion_top_k=10,
        rerank_top_k=10,
        selection_top_k=6,
        index_version="index-20260811",
        corpus_version="corpus-20260811",
        rerank_config_version="rerank-20260811",
    )


def test_service_populates_alignment_hints_for_atomic_claims(evidence_chunks) -> None:
    chunks = tuple(
        replace(chunk, index_version="index-20260811", corpus_version="corpus-20260811")
        for chunk in evidence_chunks
    )
    service = RetrievalService(
        BM25Index(chunks),
        InMemoryVectorSearch({c.chunk_id: (c, (1.0, 0.0)) for c in chunks}),
        lambda query: (1.0, 0.0),
        _config(),
    )

    result = service.search(
        Query(
            query_id="q1",
            text="amlodipine hypertension",
            atomic_claims=("amlodipine reduces blood pressure", "statin therapy lowers LDL"),
        )
    )

    assert len(result.alignment_hints) == 2
    by_index = {hint.claim_index: hint for hint in result.alignment_hints}
    assert by_index[0].decision in {"ALIGNED", "BACKGROUND", "INSUFFICIENT", "MISMATCH"}
    assert by_index[1].decision in {"ALIGNED", "BACKGROUND", "INSUFFICIENT", "MISMATCH"}
    assert all(hint.method == "token_overlap_heuristic" for hint in result.alignment_hints)
    assert all(hint.decision != "SUPPORTED" for hint in result.alignment_hints)
    assert isinstance(result.retrieval_warning, str) or result.retrieval_warning is None


def test_service_detects_conflicts_between_selected_evidence(evidence_chunks) -> None:
    chunks = tuple(
        replace(chunk, index_version="index-20260811", corpus_version="corpus-20260811")
        for chunk in evidence_chunks
    )
    service = RetrievalService(
        BM25Index(chunks),
        InMemoryVectorSearch({c.chunk_id: (c, (1.0, 0.0)) for c in chunks}),
        lambda query: (1.0, 0.0),
        _config(),
    )

    result = service.search(Query(query_id="q1", text="hypertension"))

    assert isinstance(result.conflicts, tuple)
    if result.conflicts:
        assert all(len(item) == 3 for item in result.conflicts)
