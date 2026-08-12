from __future__ import annotations

import pytest

from retrieval.fusion import fuse_rrf
from retrieval.models import EvidenceChunk, ScoredChunk


def _scored(chunk: EvidenceChunk, *, score: float, rank: int, stage: str) -> ScoredChunk:
    return ScoredChunk(chunk=chunk, score=score, rank=rank, stage=stage)


def test_fuse_rrf_promotes_overlapping_candidate_and_retains_single_channel_candidates(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    amlodipine, losartan, chinese = evidence_chunks

    candidates = fuse_rrf(
        bm25=[
            _scored(amlodipine, score=8.0, rank=1, stage="bm25"),
            _scored(losartan, score=5.0, rank=2, stage="bm25"),
        ],
        vector=[
            _scored(amlodipine, score=0.91, rank=2, stage="vector"),
            _scored(chinese, score=0.88, rank=1, stage="vector"),
        ],
        rrf_k=60,
        candidate_limit=10,
    )

    assert [candidate.chunk.chunk_id for candidate in candidates] == [
        "chunk-amlodipine",
        "chunk-chinese",
        "chunk-losartan",
    ]
    assert candidates[0].bm25_rank == 1
    assert candidates[0].vector_rank == 2
    assert candidates[0].bm25_raw_score == 8.0
    assert candidates[0].vector_raw_score == 0.91
    assert candidates[1].bm25_rank is None
    assert candidates[1].vector_rank == 1
    assert candidates[2].bm25_rank == 2
    assert candidates[2].vector_rank is None


def test_fuse_rrf_calculates_rank_only_formula_and_preserves_channel_scores(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    amlodipine, losartan, _ = evidence_chunks

    candidates = fuse_rrf(
        bm25=[_scored(amlodipine, score=13.2, rank=2, stage="bm25")],
        vector=[
            _scored(amlodipine, score=0.7, rank=5, stage="vector"), _scored(losartan, score=0.2, rank=1, stage="vector")],
        rrf_k=10,
        candidate_limit=10,
    )

    by_id = {candidate.chunk.chunk_id: candidate for candidate in candidates}
    assert by_id["chunk-amlodipine"].rrf_score == pytest.approx(1 / 12 + 1 / 15)
    assert by_id["chunk-amlodipine"].bm25_raw_score == 13.2
    assert by_id["chunk-amlodipine"].vector_raw_score == 0.7
    assert by_id["chunk-losartan"].rrf_score == pytest.approx(1 / 11)
    assert by_id["chunk-losartan"].bm25_raw_score is None


def test_fuse_rrf_sorts_equal_scores_by_chunk_id_deterministically(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    amlodipine, losartan, _ = evidence_chunks

    candidates = fuse_rrf(
        bm25=[_scored(losartan, score=2.0, rank=1, stage="bm25"), _scored(amlodipine, score=1.0, rank=1, stage="bm25")],
        vector=[],
        rrf_k=60,
        candidate_limit=10,
    )

    assert [candidate.chunk.chunk_id for candidate in candidates] == ["chunk-amlodipine", "chunk-losartan"]


def test_fuse_rrf_applies_candidate_limit_after_merging(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    amlodipine, losartan, chinese = evidence_chunks

    candidates = fuse_rrf(
        bm25=[_scored(amlodipine, score=3.0, rank=1, stage="bm25"), _scored(losartan, score=2.0, rank=2, stage="bm25")],
        vector=[_scored(chinese, score=0.9, rank=1, stage="vector")],
        rrf_k=60,
        candidate_limit=2,
    )

    assert len(candidates) == 2
    assert [candidate.chunk.chunk_id for candidate in candidates] == ["chunk-amlodipine", "chunk-chinese"]


@pytest.mark.parametrize("rrf_k,candidate_limit", [(0, 1), (1, 0), (True, 1), (1, False)])
def test_fuse_rrf_rejects_nonpositive_or_boolean_limits(rrf_k: int, candidate_limit: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        fuse_rrf([], [], rrf_k=rrf_k, candidate_limit=candidate_limit)


def test_fuse_rrf_rejects_a_wrong_channel_stage(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    with pytest.raises(ValueError, match="bm25.*stage"):
        fuse_rrf(
            [_scored(evidence_chunks[0], score=1.0, rank=1, stage="vector")],
            [],
            rrf_k=60,
            candidate_limit=10,
        )


def test_fuse_rrf_rejects_duplicate_chunk_ids_in_one_channel(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    with pytest.raises(ValueError, match="duplicate chunk_id.*bm25"):
        fuse_rrf(
            [
                _scored(evidence_chunks[0], score=2.0, rank=1, stage="bm25"),
                _scored(evidence_chunks[0], score=1.0, rank=2, stage="bm25"),
            ],
            [],
            rrf_k=60,
            candidate_limit=10,
        )


def test_fuse_rrf_rejects_same_id_with_different_evidence_metadata(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    original = evidence_chunks[0]
    conflicting = EvidenceChunk(
        chunk_id=original.chunk_id,
        evidence_id="different-evidence-id",
        stable_id=original.stable_id,
        text=original.text,
    )

    with pytest.raises(ValueError, match="different EvidenceChunk"):
        fuse_rrf(
            [_scored(original, score=1.0, rank=1, stage="bm25")],
            [_scored(conflicting, score=0.9, rank=1, stage="vector")],
            rrf_k=60,
            candidate_limit=10,
        )


def test_fuse_rrf_rejects_mutated_nonpositive_rank(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    malformed = _scored(evidence_chunks[0], score=1.0, rank=1, stage="bm25")
    object.__setattr__(malformed, "rank", 0)

    with pytest.raises(ValueError, match="rank"):
        fuse_rrf([malformed], [], rrf_k=60, candidate_limit=10)


def test_fuse_rrf_rejects_a_mutated_non_float_representable_score(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    malformed = _scored(evidence_chunks[0], score=1.0, rank=1, stage="bm25")
    object.__setattr__(malformed, "score", 10**10000)

    with pytest.raises(ValueError, match="score"):
        fuse_rrf([malformed], [], rrf_k=60, candidate_limit=10)


def test_fuse_rrf_rejects_non_float_representable_rrf_k(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    with pytest.raises(ValueError, match="rrf_k"):
        fuse_rrf(
            [_scored(evidence_chunks[0], score=1.0, rank=1, stage="bm25")],
            [],
            rrf_k=10**10000,
            candidate_limit=10,
        )


def test_fuse_rrf_rejects_a_mutated_non_float_representable_rank(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    malformed = _scored(evidence_chunks[0], score=1.0, rank=1, stage="bm25")
    object.__setattr__(malformed, "rank", 10**10000)

    with pytest.raises(ValueError, match="rank"):
        fuse_rrf([malformed], [], rrf_k=60, candidate_limit=10)
