"""Behavioral tests for the BGE-M3 dense embedding integration.

Tests inject an A3-style provider: A4 cannot construct or download a model.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
import math

import pytest

from retrieval.bge_m3 import BgeM3Embedder, BgeM3EmbeddingError
from retrieval.bm25 import BM25Index
from retrieval.config import RetrievalConfig
from retrieval.models import EvidenceChunk, Query, SearchStatus
from retrieval.service import RetrievalService
from retrieval.vector import InMemoryVectorSearch


class FakeProvider:
    """Deterministic stand-in for A3 ``EmbeddingProvider``."""

    def __init__(self, vectors: Sequence[Sequence[float]] | Callable[[list[str]], list[Sequence[float]]]) -> None:
        self._vectors = vectors
        self.query_calls: list[list[str]] = []
        self.document_calls: list[list[str]] = []

    @property
    def model_id(self) -> str:
        return "upstream:MOCK-A3-EMBEDDING"

    @property
    def revision(self) -> str | None:
        return "fixture-v1"

    @property
    def source_kind(self) -> str:
        return "fixture"

    def _encode(self, texts: object) -> list[list[float]]:
        items = list(texts)  # type: ignore[arg-type]
        if callable(self._vectors):
            return [list(row) for row in self._vectors(items)]
        return [list(self._vectors[index % len(self._vectors)]) for index in range(len(items))]

    def encode_queries(self, texts: object) -> list[list[float]]:
        items = list(texts)  # type: ignore[arg-type]
        self.query_calls.append(items)
        return self._encode(items)

    def encode_documents(self, texts: object) -> list[list[float]]:
        items = list(texts)  # type: ignore[arg-type]
        self.document_calls.append(items)
        return self._encode(items)


def _chunk(chunk_id: str, *, title: str = "", text: str = "Clinical evidence snippet.") -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        evidence_id=f"evidence-{chunk_id}",
        stable_id=f"upstream:MOCK-A4-{chunk_id}",
        title=title,
        text=text,
        source_type="pubmed",
        evidence_level="rct",
        index_version="index-20260811",
        corpus_version="corpus-20260811",
        mock=True,
    )


def _embedder(fake: FakeProvider) -> BgeM3Embedder:
    return BgeM3Embedder(fake, capability_enabled=True)


def test_bge_m3_adapter_is_pending_by_default_and_never_loads_a_model() -> None:
    provider = FakeProvider([(1.0, 0.0)])
    embedder = BgeM3Embedder(provider)

    with pytest.raises(BgeM3EmbeddingError, match="PENDING"):
        embedder.encode_query(Query(query_id="q1", text="氨氯地平"))

    assert provider.query_calls == []


def test_bge_m3_encode_query_requests_normalized_encoding_of_query_text() -> None:
    fake = FakeProvider([(3.0, 4.0)])
    embedder = _embedder(fake)

    vector = embedder.encode_query(Query(query_id="q1", text="老年高血压的一线降压治疗"))

    assert fake.query_calls == [["老年高血压的一线降压治疗"]]
    assert vector == (3.0, 4.0)


def test_bge_m3_build_vector_search_encodes_title_plus_text_with_normalization() -> None:
    fake = FakeProvider([(1.0, 0.0)])
    embedder = _embedder(fake)
    chunks = (
        _chunk("c1", title="Amlodipine for hypertension", text="A randomized trial."),
        _chunk("c2", title="", text="Chinese evidence."),
    )

    search = embedder.build_vector_search(chunks)

    assert isinstance(search, InMemoryVectorSearch)
    assert fake.document_calls == [
        ["Amlodipine for hypertension A randomized trial.", "Chinese evidence."]
    ]


def test_bge_m3_built_search_ranks_semantically_closer_chunk_first() -> None:
    embedder = _embedder(FakeProvider([(1.0, 0.0), (0.0, 1.0)]))
    search = embedder.build_vector_search((_chunk("c-drug"), _chunk("c-other")))

    results = search.search((0.9, 0.1), k=2)

    assert results[0].chunk.chunk_id == "c-drug"
    assert results[0].stage == "vector"


def test_bge_m3_encoding_failure_raises_stable_error() -> None:
    class ExplodingProvider(FakeProvider):
        def encode_queries(self, texts: object) -> list[list[float]]:
            raise ValueError("provider exploded")

    embedder = _embedder(ExplodingProvider([]))

    with pytest.raises(BgeM3EmbeddingError, match="bge_m3"):
        embedder.encode_query(Query(query_id="q1", text="x"))


def test_bge_m3_build_rejects_dimension_mismatch() -> None:
    def vectors(texts: list[str]) -> list[Sequence[float]]:
        if len(texts) == 1:
            return [[1.0, 0.0]]
        return [[0.0, 1.0, 0.0], [1.0, 0.0]]

    embedder = _embedder(FakeProvider(vectors))

    with pytest.raises(BgeM3EmbeddingError, match="dimension"):
        embedder.build_vector_search((_chunk("c1"), _chunk("c2")))


def test_bge_m3_build_rejects_count_mismatch() -> None:
    def always_one_row(_texts: list[str]) -> list[Sequence[float]]:
        return [[1.0, 0.0]]

    embedder = _embedder(FakeProvider(always_one_row))

    with pytest.raises(BgeM3EmbeddingError, match="count"):
        embedder.build_vector_search((_chunk("c1"), _chunk("c2")))


@pytest.mark.parametrize("vector", [(math.inf, 0.0), (0.0, math.nan)])
def test_bge_m3_build_rejects_nonfinite_outputs(vector: tuple[float, float]) -> None:
    embedder = _embedder(FakeProvider([vector]))

    with pytest.raises(BgeM3EmbeddingError, match="finite"):
        embedder.build_vector_search((_chunk("c1"),))


def test_bge_m3_encode_query_rejects_nonfinite_output() -> None:
    embedder = _embedder(FakeProvider([(math.nan, 1.0)]))

    with pytest.raises(BgeM3EmbeddingError, match="finite"):
        embedder.encode_query(Query(query_id="q1", text="x"))


def test_bge_m3_empty_corpus_builds_empty_search_without_encoding() -> None:
    fake = FakeProvider([(1.0, 0.0)])
    embedder = _embedder(fake)

    search = embedder.build_vector_search(())

    assert search.search((1.0, 0.0), k=5) == []
    assert fake.document_calls == []


def test_bge_m3_built_search_ignores_zero_norm_corpus_vectors() -> None:
    embedder = _embedder(FakeProvider([(0.0, 0.0), (1.0, 0.0)]))
    search = embedder.build_vector_search((_chunk("c-zero"), _chunk("c-drug")))

    results = search.search((0.9, 0.1), k=2)

    assert [result.chunk.chunk_id for result in results] == ["c-drug"]


def test_retrieval_service_reports_partial_when_bge_m3_embedding_fails(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    chunks = tuple(
        replace(chunk, index_version="index-20260811", corpus_version="corpus-20260811")
        for chunk in evidence_chunks
    )

    def failing_provider(_query: Query) -> Sequence[float]:
        raise BgeM3EmbeddingError("bge_m3 model could not be loaded: RuntimeError")

    service = RetrievalService(
        bm25_index=BM25Index(chunks),
        vector_search=InMemoryVectorSearch({}),
        query_vector_provider=failing_provider,
        config=RetrievalConfig(
            index_version="index-20260811",
            corpus_version="corpus-20260811",
            rerank_config_version="rerank-20260811",
        ),
    )

    result = service.search(Query(query_id="q1", text="amlodipine"))

    assert result.status is SearchStatus.PARTIAL
    assert any("vector" in reason for reason in result.degradation_reasons)
    assert result.selected_chunks  # BM25-only degradation still returns evidence
