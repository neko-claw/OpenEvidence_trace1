"""Local BGE-M3 dense embedding integration for A4 vector retrieval.

``BgeM3Embedder`` is the only component aware of ``sentence-transformers``.
It lazily loads ``BAAI/bge-m3``, batch-encodes ``title + text`` into L2
normalized dense vectors, and builds records consumable by the existing
``InMemoryVectorSearch``.  A model factory may be injected to pin cache
directory, device, or offline behavior in deployment; tests inject a fake
factory so no model is ever downloaded during the test run.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from math import isfinite
from numbers import Real
from typing import Any

from .models import EvidenceChunk, Query
from .vector import InMemoryVectorSearch


class BgeM3EmbeddingError(Exception):
    """Stable error raised when BGE-M3 model loading or encoding fails.

    The message prefix ``"bge_m3"`` is part of the public contract; the
    service layer maps any such failure to the existing ``vector_unavailable``
    degradation path without leaking provider internals.
    """


class BgeM3Embedder:
    """Lazy, dependency-isolated dense embedder over SentenceTransformer BGE-M3."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        model_factory: Callable[[str], Any] | None = None,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name must be a nonblank string")
        if model_factory is not None and not callable(model_factory):
            raise ValueError("model_factory must be callable or None")
        self._model_name = model_name
        self._model_factory = model_factory
        self._model: Any = None

    def encode_query(self, query: Query) -> tuple[float, ...]:
        """Encode one query's text into a finite dense vector.

        The model is loaded on first use; a load or encoding failure raises
        ``BgeM3EmbeddingError`` so the service can report ``partial``/``failed``
        instead of silently degrading to a fabricated vector.
        """
        if not isinstance(query, Query):
            raise ValueError("query must be a Query")
        model = self._ensure_model()
        try:
            rows = _as_vector_rows(model.encode([query.text], normalize_embeddings=True))
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

        model = self._ensure_model()
        texts = [f"{chunk.title} {chunk.text}".strip() for chunk in normalized]
        try:
            rows = _as_vector_rows(model.encode(texts, normalize_embeddings=True))
            _validate_rows(rows, expected=len(normalized), label="corpus")
        except BgeM3EmbeddingError:
            raise
        except Exception as error:
            raise BgeM3EmbeddingError(f"bge_m3 encode failed: {type(error).__name__}") from error

        return InMemoryVectorSearch(
            (chunk.chunk_id, chunk, rows[index]) for index, chunk in enumerate(normalized)
        )

    def _ensure_model(self) -> Any:
        if self._model is None:
            factory = self._model_factory if self._model_factory is not None else _default_model_factory
            try:
                self._model = factory(self._model_name)
            except Exception as error:
                raise BgeM3EmbeddingError(
                    f"bge_m3 model could not be loaded: {type(error).__name__}"
                ) from error
        return self._model


def _default_model_factory(model_name: str) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


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
