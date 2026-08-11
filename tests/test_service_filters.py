"""Tests for tiered-retrieval metadata filtering in the service (4.1)."""

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
        selection_top_k=4,
        index_version="index-20260811",
        corpus_version="corpus-20260811",
        rerank_config_version="rerank-20260811",
    )


def _service(chunks) -> RetrievalService:
    return RetrievalService(
        BM25Index(chunks),
        InMemoryVectorSearch({c.chunk_id: (c, (1.0, 0.0)) for c in chunks}),
        lambda query: (1.0, 0.0),
        _config(),
    )


def test_service_filters_by_topic(evidence_chunks) -> None:
    chunks = tuple(
        replace(chunk, index_version="index-20260811", corpus_version="corpus-20260811", topic="hypertension")
        for chunk in evidence_chunks
    )
    service = _service(chunks)

    result = service.search(Query(query_id="q1", text="amlodipine", domain="hypertension"))

    assert result.status.value == "ok"
    assert all(c.topic == "hypertension" for c in result.selected_chunks)


def test_service_excludes_untagged_chunks_when_topic_is_requested(evidence_chunks) -> None:
    chunks = tuple(
        replace(chunk, index_version="index-20260811", corpus_version="corpus-20260811")
        for chunk in evidence_chunks
    )
    service = _service(chunks)

    result = service.search(Query(query_id="q1", text="amlodipine", domain="hypertension"))

    assert result.selected_chunks == ()


def test_service_filters_by_source_types(evidence_chunks) -> None:
    chunks = tuple(
        replace(chunk, index_version="index-20260811", corpus_version="corpus-20260811")
        for chunk in evidence_chunks
    )
    service = _service(chunks)

    result = service.search(
        Query(query_id="q1", text="高血压", source_types=("guideline",))
    )

    assert all(c.source_type == "guideline" for c in result.selected_chunks)


def test_service_filters_by_evidence_levels(evidence_chunks) -> None:
    chunks = tuple(
        replace(chunk, index_version="index-20260811", corpus_version="corpus-20260811")
        for chunk in evidence_chunks
    )
    service = _service(chunks)

    result = service.search(
        Query(query_id="q1", text="治疗", evidence_levels=("guideline",))
    )

    assert all(c.evidence_level == "guideline" for c in result.selected_chunks)


def test_service_filters_apply_to_both_recall_channels(evidence_chunks) -> None:
    chunks = tuple(
        replace(chunk, index_version="index-20260811", corpus_version="corpus-20260811")
        for chunk in evidence_chunks
    )
    service = _service(chunks)

    result = service.search(
        Query(query_id="q1", text="降压治疗", source_types=("pubmed",), evidence_levels=("rct",))
    )

    assert result.selected_chunks
    assert all(c.source_type == "pubmed" and c.evidence_level == "rct" for c in result.selected_chunks)
