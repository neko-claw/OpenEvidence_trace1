"""Deterministic in-memory vector retrieval primitives."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from math import hypot, isfinite
from numbers import Real
from typing import Protocol, runtime_checkable

from .models import EvidenceChunk, ScoredChunk


@runtime_checkable
class VectorSearch(Protocol):
    """Interface implemented by vector candidate retrievers."""

    def search(self, query_vector: Sequence[float], k: int) -> list[ScoredChunk]:
        """Return up to ``k`` semantic candidates in deterministic rank order."""


VectorRecord = tuple[str, EvidenceChunk, Sequence[float]]
VectorMapping = Mapping[str, tuple[EvidenceChunk, Sequence[float]]]


class InMemoryVectorSearch:
    """Cosine similarity search for a small, validated evidence-vector corpus."""

    def __init__(self, records: VectorMapping | Iterable[VectorRecord]) -> None:
        normalized_records = self._normalize_records(records)
        if not normalized_records:
            self._dimension = None
            self._records: tuple[tuple[EvidenceChunk, tuple[float, ...], float], ...] = ()
            return

        dimension = len(normalized_records[0][2])
        if any(len(vector) != dimension for _, _, vector in normalized_records):
            raise ValueError("all vectors must have the same dimension")
        self._dimension = dimension
        self._records = tuple(
            (chunk, vector, _norm(vector)) for _, chunk, vector in normalized_records
        )

    def search(self, query_vector: Sequence[float], k: int) -> list[ScoredChunk]:
        """Find positive-cosine neighbors, excluding undefined zero-norm corpus vectors."""
        if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
            raise ValueError("k must be a positive integer")
        vector = _normalize_vector(query_vector, "query_vector")
        query_norm = _norm(vector)
        if query_norm == 0:
            raise ValueError("query_vector must not be a zero vector")
        if self._dimension is None:
            return []
        if len(vector) != self._dimension:
            raise ValueError("query_vector dimension must match corpus vectors")

        scored: list[tuple[EvidenceChunk, float]] = []
        for chunk, corpus_vector, corpus_norm in self._records:
            if corpus_norm == 0:
                continue
            score = sum(
                (left / query_norm) * (right / corpus_norm)
                for left, right in zip(vector, corpus_vector, strict=True)
            )
            if score > 0:
                scored.append((chunk, score))
        scored.sort(key=lambda item: (-item[1], item[0].chunk_id))
        return [
            ScoredChunk(chunk=chunk, score=score, rank=rank, stage="vector")
            for rank, (chunk, score) in enumerate(scored[:k], start=1)
        ]

    @staticmethod
    def _normalize_records(records: VectorMapping | Iterable[VectorRecord]) -> tuple[VectorRecord, ...]:
        if isinstance(records, Mapping):
            raw_records: Iterable[object] = (
                (chunk_id, chunk, vector) for chunk_id, (chunk, vector) in records.items()
            )
        else:
            raw_records = records

        try:
            candidates = tuple(raw_records)
        except TypeError as error:
            raise ValueError("records must be a mapping or iterable of vector records") from error

        normalized: list[VectorRecord] = []
        seen_chunk_ids: set[str] = set()
        for candidate in candidates:
            try:
                chunk_id, chunk, vector = candidate  # type: ignore[misc]
            except (TypeError, ValueError) as error:
                raise ValueError("each vector record must contain chunk_id, EvidenceChunk, and vector") from error
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                raise ValueError("chunk_id must be a nonblank string")
            if chunk_id in seen_chunk_ids:
                raise ValueError("duplicate chunk_id in vector search")
            if not isinstance(chunk, EvidenceChunk):
                raise ValueError("each vector record must contain an EvidenceChunk")
            if chunk.chunk_id != chunk_id:
                raise ValueError("vector record chunk_id must match EvidenceChunk.chunk_id")
            seen_chunk_ids.add(chunk_id)
            normalized.append((chunk_id, chunk, _normalize_vector(vector, "vector")))
        return tuple(normalized)


def _normalize_vector(value: Sequence[float], field_name: str) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be a nonempty numeric sequence")
    try:
        vector = tuple(value)
    except TypeError as error:
        raise ValueError(f"{field_name} must be a nonempty numeric sequence") from error
    if not vector:
        raise ValueError(f"{field_name} must be a nonempty numeric sequence")
    if any(not isinstance(number, Real) or isinstance(number, bool) or not isfinite(number) for number in vector):
        raise ValueError(f"{field_name} must contain only finite numbers")
    return tuple(float(number) for number in vector)


def _norm(vector: Sequence[float]) -> float:
    return hypot(*vector)
