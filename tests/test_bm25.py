from __future__ import annotations

import pytest

from retrieval.bm25 import BM25Index
from retrieval.models import EvidenceChunk


def test_bm25_ranks_exact_drug_mention_first(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    index = BM25Index(evidence_chunks)

    results = index.search("amlodipine hypertension", k=3)

    assert results[0].chunk.chunk_id == "chunk-amlodipine"
    assert results[0].stage == "bm25"
    assert [result.rank for result in results] == [1, 2]


def test_bm25_matches_contiguous_chinese_terms(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    index = BM25Index(evidence_chunks)

    results = index.search("老年高血压", k=3)

    assert results[0].chunk.chunk_id == "chunk-chinese"
    assert results[0].score > 0


def test_bm25_matches_overlapping_chinese_phrases() -> None:
    index = BM25Index(
        (EvidenceChunk("chunk-chinese-overlap", "e-chinese-overlap", "GUIDELINE:4", "老年高血压患者用药建议"),)
    )

    results = index.search("老年高血压", k=1)

    assert [result.chunk.chunk_id for result in results] == ["chunk-chinese-overlap"]


def test_bm25_does_not_match_reordered_chinese_characters() -> None:
    index = BM25Index((EvidenceChunk("chunk-reordered", "e-reordered", "GUIDELINE:5", "压血高年老"),))

    assert index.search("老年高血压", k=1) == []


def test_bm25_does_not_match_a_single_chinese_character() -> None:
    index = BM25Index((EvidenceChunk("chunk-single-cjk", "e-single-cjk", "GUIDELINE:6", "年"),))

    assert index.search("年", k=1) == []


def test_bm25_orders_equal_scores_by_chunk_id() -> None:
    index = BM25Index(
        (
            EvidenceChunk("chunk-b", "e-b", "PMID:2", "hypertension"),
            EvidenceChunk("chunk-a", "e-a", "PMID:1", "hypertension"),
        )
    )

    results = index.search("hypertension", k=2)

    assert [result.chunk.chunk_id for result in results] == ["chunk-a", "chunk-b"]


def test_bm25_returns_no_match_safely_and_handles_documents_with_no_tokens() -> None:
    index = BM25Index((EvidenceChunk("chunk-symbols", "e-symbols", "PMID:3", "!!!"),))

    assert index.search("unseen", k=5) == []
    assert index.search("!!!", k=5) == []


def test_bm25_counts_document_frequency_once_per_document() -> None:
    index = BM25Index((EvidenceChunk("chunk-aspirin", "e-aspirin", "PMID:7", "aspirin aspirin"),))

    results = index.search("aspirin", k=1)

    assert [result.chunk.chunk_id for result in results] == ["chunk-aspirin"]
    assert results[0].score > 0


@pytest.mark.parametrize("query,k", [(" ", 1), ("hypertension", 0)])
def test_bm25_rejects_blank_queries_and_nonpositive_k(query: str, k: int) -> None:
    index = BM25Index(())

    with pytest.raises(ValueError):
        index.search(query, k=k)


def test_bm25_rejects_duplicate_chunk_ids(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    duplicate = EvidenceChunk("chunk-amlodipine", "e-other", "PMID:other", "other text")

    with pytest.raises(ValueError, match="duplicate"):
        BM25Index((*evidence_chunks, duplicate))


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("k1", True),
        ("k1", False),
        ("k1", float("nan")),
        ("k1", float("inf")),
        ("k1", -float("inf")),
        ("k1", 0.0),
        ("k1", -0.1),
        ("b", True),
        ("b", False),
        ("b", float("nan")),
        ("b", float("inf")),
        ("b", -float("inf")),
        ("b", -0.1),
        ("b", 1.1),
    ],
)
def test_bm25_rejects_invalid_k1_and_b_values(parameter: str, value: float) -> None:
    with pytest.raises(ValueError):
        BM25Index((), **{parameter: value})
