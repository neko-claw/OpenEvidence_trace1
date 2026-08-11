from __future__ import annotations

from dataclasses import replace
import math

import pytest

from retrieval.models import EvidenceChunk
from retrieval.vector import InMemoryVectorSearch, VectorSearch


def test_vector_search_returns_cosine_nearest_neighbor(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    amlodipine, losartan, chinese = evidence_chunks
    search: VectorSearch = InMemoryVectorSearch(
        {
            "chunk-amlodipine": (amlodipine, (1.0, 0.0)),
            "chunk-losartan": (losartan, (0.8, 0.2)),
            "chunk-chinese": (chinese, (0.0, 1.0)),
        }
    )

    results = search.search((0.95, 0.05), k=3)

    assert results[0].chunk.chunk_id == "chunk-amlodipine"
    assert results[0].stage == "vector"
    assert results[0].score == pytest.approx(0.9986, abs=0.0001)


def test_vector_search_handles_finite_large_components_without_overflow(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    search = InMemoryVectorSearch({"chunk-amlodipine": (evidence_chunks[0], (1e308, 1e308))})

    results = search.search((1e308, 1e308), k=1)

    assert [result.chunk.chunk_id for result in results] == ["chunk-amlodipine"]
    assert results[0].score == pytest.approx(1.0)


def test_vector_search_rejects_query_dimension_mismatch(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    search = InMemoryVectorSearch({"chunk-amlodipine": (evidence_chunks[0], (1.0, 0.0))})

    with pytest.raises(ValueError, match="dimension"):
        search.search((1.0, 0.0, 0.0), k=1)


def test_vector_search_orders_equal_cosine_scores_by_chunk_id(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    chunk_b = replace(evidence_chunks[0], chunk_id="chunk-b")
    chunk_a = replace(evidence_chunks[1], chunk_id="chunk-a")
    search = InMemoryVectorSearch(
        {
            "chunk-b": (chunk_b, (1.0, 0.0)),
            "chunk-a": (chunk_a, (1.0, 0.0)),
        }
    )

    results = search.search((1.0, 0.0), k=2)

    assert [result.chunk.chunk_id for result in results] == ["chunk-a", "chunk-b"]


def test_vector_search_rejects_zero_query_vector(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    search = InMemoryVectorSearch({"chunk-amlodipine": (evidence_chunks[0], (1.0, 0.0))})

    with pytest.raises(ValueError, match="zero"):
        search.search((0.0, 0.0), k=1)


def test_vector_search_rejects_zero_query_vector_for_an_empty_corpus() -> None:
    search = InMemoryVectorSearch({})

    with pytest.raises(ValueError, match="zero"):
        search.search((0.0,), k=1)


def test_vector_search_skips_zero_norm_corpus_vectors(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    search = InMemoryVectorSearch({"chunk-amlodipine": (evidence_chunks[0], (0.0, 0.0))})

    assert search.search((1.0, 0.0), k=1) == []


def test_vector_search_rejects_duplicate_chunk_ids(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    records = (
        ("chunk-amlodipine", evidence_chunks[0], (1.0, 0.0)),
        ("chunk-amlodipine", evidence_chunks[1], (0.0, 1.0)),
    )

    with pytest.raises(ValueError, match="duplicate"):
        InMemoryVectorSearch(records)


@pytest.mark.parametrize("query", [(math.inf, 0.0), (1.0, math.nan)])
def test_vector_search_rejects_nonfinite_query_values(
    evidence_chunks: tuple[EvidenceChunk, ...], query: tuple[float, float]
) -> None:
    search = InMemoryVectorSearch({"chunk-amlodipine": (evidence_chunks[0], (1.0, 0.0))})

    with pytest.raises(ValueError, match="finite"):
        search.search(query, k=1)


def test_vector_search_rejects_nonpositive_k(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    search = InMemoryVectorSearch({"chunk-amlodipine": (evidence_chunks[0], (1.0, 0.0))})

    with pytest.raises(ValueError):
        search.search((1.0, 0.0), k=0)
