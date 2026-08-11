"""Deterministic reciprocal-rank fusion for A4 retrieval candidates."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from numbers import Real

from .models import MAX_RRF_OPERAND, Candidate, EvidenceChunk, ScoredChunk


def fuse_rrf(
    bm25: Sequence[ScoredChunk],
    vector: Sequence[ScoredChunk],
    rrf_k: int,
    candidate_limit: int,
) -> list[Candidate]:
    """Merge BM25 and vector candidates using rank-only reciprocal-rank fusion.

    The returned ``rrf_score`` is a retrieval score only.  It is not a clinical
    evidence-quality signal and is retained separately from each channel's raw
    retrieval score for later audit and reranking.
    """
    _require_positive_int(rrf_k, "rrf_k")
    _require_positive_int(candidate_limit, "candidate_limit")

    bm25_by_id = _validate_channel(bm25, expected_stage="bm25", channel_name="bm25")
    vector_by_id = _validate_channel(vector, expected_stage="vector", channel_name="vector")

    candidates: list[Candidate] = []
    for chunk_id in sorted(set(bm25_by_id) | set(vector_by_id)):
        bm25_item = bm25_by_id.get(chunk_id)
        vector_item = vector_by_id.get(chunk_id)
        chunk = _merge_chunk(chunk_id, bm25_item, vector_item)
        rrf_score = sum(
            1 / (rrf_k + item.rank)
            for item in (bm25_item, vector_item)
            if item is not None
        )
        candidates.append(
            Candidate(
                chunk=chunk,
                bm25_rank=bm25_item.rank if bm25_item is not None else None,
                vector_rank=vector_item.rank if vector_item is not None else None,
                bm25_raw_score=bm25_item.score if bm25_item is not None else None,
                vector_raw_score=vector_item.score if vector_item is not None else None,
                rrf_score=rrf_score,
            )
        )

    candidates.sort(key=lambda candidate: (-candidate.rrf_score, candidate.chunk.chunk_id))
    return candidates[:candidate_limit]


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0 or value > MAX_RRF_OPERAND:
        raise ValueError(f"{field_name} must be a positive integer within the float-representable domain")


def _is_float_representable_finite(value: object) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _validate_channel(
    values: Sequence[ScoredChunk], *, expected_stage: str, channel_name: str
) -> dict[str, ScoredChunk]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{channel_name} must be a sequence of ScoredChunk")

    by_id: dict[str, ScoredChunk] = {}
    for item in values:
        if not isinstance(item, ScoredChunk):
            raise ValueError(f"{channel_name} must contain only ScoredChunk values")
        if item.stage != expected_stage:
            raise ValueError(f"{channel_name} candidates must have stage {expected_stage!r}")
        if (
            not isinstance(item.rank, int)
            or isinstance(item.rank, bool)
            or item.rank < 1
            or item.rank > MAX_RRF_OPERAND
        ):
            raise ValueError(f"{channel_name} candidate rank must be a positive integer within the float-representable domain")
        if not _is_float_representable_finite(item.score) or item.score < 0:
            raise ValueError(f"{channel_name} candidate score must be a finite nonnegative number")
        if not isinstance(item.chunk, EvidenceChunk):
            raise ValueError(f"{channel_name} candidate chunk must be an EvidenceChunk")
        chunk_id = item.chunk.chunk_id
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError(f"{channel_name} candidate chunk_id must be a nonblank string")
        if chunk_id in by_id:
            raise ValueError(f"duplicate chunk_id in {channel_name} candidates: {chunk_id}")
        by_id[chunk_id] = item
    return by_id


def _merge_chunk(
    chunk_id: str, bm25_item: ScoredChunk | None, vector_item: ScoredChunk | None
) -> EvidenceChunk:
    if bm25_item is None:
        assert vector_item is not None
        return vector_item.chunk
    if vector_item is None:
        return bm25_item.chunk
    if bm25_item.chunk != vector_item.chunk:
        raise ValueError(f"chunk_id {chunk_id!r} refers to different EvidenceChunk metadata across channels")
    return bm25_item.chunk
