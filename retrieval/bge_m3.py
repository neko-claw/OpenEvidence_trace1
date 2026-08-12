"""Compatibility adapter from A3's EmbeddingProvider into A4 retrieval.

A4 deliberately does not load BGE-M3 (or any other embedding model).  Model
selection, revision pinning, indexing, and DEV Recall@50 validation belong to
A3.  This module only consumes an already-constructed A3 provider when the
versioned capability switch is explicitly enabled.
"""

from __future__ import annotations

from collections.abc import Iterable
from math import isfinite
from numbers import Real

from a3.indexing.embeddings import EmbeddingProvider

from .models import EvidenceChunk, Query
from .vector import InMemoryVectorSearch


class BgeM3EmbeddingError(Exception):
    """Stable error raised when BGE-M3 model loading or encoding fails.

    The message prefix ``"bge_m3"`` is part of the public contract; the
    service layer maps any such failure to the existing ``vector_unavailable``
    degradation path without leaking provider internals.
    """


class A3EmbeddingAdapter:
    """Consume A3's provider without constructing or downloading a model."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        *,
        capability_enabled: bool = False,
    ) -> None:
        if not callable(getattr(provider, "encode_queries", None)) or not callable(
            getattr(provider, "encode_documents", None)
        ):
            raise ValueError("provider must implement the A3 EmbeddingProvider contract")
        if not isinstance(capability_enabled, bool):
            raise ValueError("capability_enabled must be bool")
        self._provider = provider
        self._capability_enabled = capability_enabled

    def encode_query(self, query: Query) -> tuple[float, ...]:
        """Encode one query's text into a finite dense vector.

        The model is loaded on first use; a load or encoding failure raises
        ``BgeM3EmbeddingError`` so the service can report ``partial``/``failed``
        instead of silently degrading to a fabricated vector.
        """
        if not isinstance(query, Query):
            raise ValueError("query must be a Query")
        self._require_enabled()
        try:
            rows = _as_vector_rows(self._provider.encode_queries([query.text]))
            _validate_rows(rows, expected=1, label="query")
        except BgeM3EmbeddingError:
            raise
        except Exception as error:
            raise BgeM3EmbeddingError(f"bge_m3 encode failed: {type(error).__name__}") from error
        return tuple(rows[0])

    def build_vector_search(self, chunks: Iterable[EvidenceChunk]) -> InMemoryVectorSearch:
        """Batch-encode ``title + text`` and build a validated in-memory vector index.

        The built index fails closed: encoded row count, dimension consistency,
        and finiteness are all validated before any record enters the search
        object, so a corrupt or partial index is never silently produced.
        """
        try:
            normalized = tuple(chunks)
        except TypeError as error:
            raise ValueError("chunks must be an iterable of EvidenceChunk") from error
        if any(not isinstance(chunk, EvidenceChunk) for chunk in normalized):
            raise ValueError("chunks must contain only EvidenceChunk values")
        if not normalized:
            return InMemoryVectorSearch({})

        self._require_enabled()
        texts = [f"{chunk.title} {chunk.text}".strip() for chunk in normalized]
        try:
            rows = _as_vector_rows(self._provider.encode_documents(texts))
            _validate_rows(rows, expected=len(normalized), label="corpus")
        except BgeM3EmbeddingError:
            raise
        except Exception as error:
            raise BgeM3EmbeddingError(f"bge_m3 encode failed: {type(error).__name__}") from error

        return InMemoryVectorSearch(
            (chunk.chunk_id, chunk, rows[index]) for index, chunk in enumerate(normalized)
        )

    def _require_enabled(self) -> None:
        if not self._capability_enabled:
            raise BgeM3EmbeddingError(
                "bge_m3 capability PENDING: enable only after A3 DEV Recall@50, latency, and rebuild validation"
            )


class BgeM3Embedder(A3EmbeddingAdapter):
    """Backward-compatible name; implementation is the A3 provider adapter."""


def _as_vector_rows(encoded: object) -> list[list[float]]:
    """Convert an encoder output into validated finite float rows."""
    if isinstance(encoded, (str, bytes)):
        raise BgeM3EmbeddingError("bge_m3 encode returned a scalar")
    try:
        rows = list(encoded)
    except TypeError as error:
        raise BgeM3EmbeddingError("bge_m3 encode returned a non-iterable value") from error
    result: list[list[float]] = []
    for row in rows:
        try:
            values = list(row)
        except TypeError as error:
            raise BgeM3EmbeddingError("bge_m3 encode returned a non-iterable row") from error
        if any(not _finite(value) for value in values):
            raise BgeM3EmbeddingError("bge_m3 encode returned non-finite values")
        result.append([float(value) for value in values])
    return result


def _validate_rows(rows: list[list[float]], *, expected: int, label: str) -> None:
    if len(rows) != expected:
        raise BgeM3EmbeddingError(
            f"bge_m3 encode count mismatch: expected {expected} {label} row(s), got {len(rows)}"
        )
    if not rows:
        return
    dimension = len(rows[0])
    if dimension == 0:
        raise BgeM3EmbeddingError("bge_m3 encode returned empty vectors")
    if any(len(row) != dimension for row in rows):
        raise BgeM3EmbeddingError("bge_m3 encode returned inconsistent vector dimensions")


def _finite(value: object) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False
