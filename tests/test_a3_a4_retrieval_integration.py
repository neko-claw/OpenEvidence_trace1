"""Blocking-contract tests for the A3 -> A4 Track-1 retrieval boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

import pytest

from retrieval.a3_pool_adapter import build_initial_pool_from_a3_hits
from retrieval.config import RetrievalConfig
from retrieval.cross_encoder import CrossEncoderScorer
from retrieval.models import EvidenceChunk, Query, RetrievalCondition, ScoredChunk, SearchStatus
from retrieval.ports import SupportGateResult
from retrieval.service import RetrievalService


def _chunk(chunk_id: str, text: str, vector: tuple[float, ...]) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        evidence_id=f"MOCK-EVIDENCE-{chunk_id}",
        stable_id=f"upstream:MOCK-A4-{chunk_id}",
        title=f"Mock title {chunk_id}",
        text=text,
        source_type="mock_fixture",
        evidence_level="mock_level",
        content_vector=vector,
        mock=True,
        index_version="mock-index-v1",
        corpus_version="mock-corpus-v1",
    )


class CountingSearch:
    def __init__(self, stage: str, chunks: Sequence[EvidenceChunk]) -> None:
        self.stage = stage
        self.chunks = tuple(chunks)
        self.calls = 0

    def search(self, _query: object, k: int) -> list[ScoredChunk]:
        self.calls += 1
        return [
            ScoredChunk(chunk=chunk, score=1.0 / rank, rank=rank, stage=self.stage)
            for rank, chunk in enumerate(self.chunks[:k], start=1)
        ]


class FakeCrossEncoder:
    def __init__(self) -> None:
        self.calls = 0

    def predict(self, pairs: object) -> list[float]:
        values = list(pairs)  # type: ignore[arg-type]
        self.calls += 1
        return [float(index) / max(1, len(values) - 1) for index in range(len(values))]


class KeepAllGate:
    def filter(self, _query: Query, candidates: Sequence[object]) -> SupportGateResult:
        return SupportGateResult(tuple(candidate.chunk.chunk_id for candidate in candidates))


class RemoveAllGate:
    def filter(self, _query: Query, _candidates: Sequence[object]) -> SupportGateResult:
        return SupportGateResult((), ("fixture_support_gate_removed_all",))


class FixedQualityScorer:
    def score(self, _query: Query, chunks: Sequence[EvidenceChunk]) -> dict[str, float]:
        return {chunk.chunk_id: 0.8 for chunk in chunks}


def _config() -> RetrievalConfig:
    return RetrievalConfig(
        bm25_top_k=3,
        vector_top_k=3,
        fusion_top_k=3,
        rerank_top_k=3,
        selection_top_k=2,
        mmr_lambda=1.0,
        evidence_type_bonus=0.0,
        cross_encoder_alpha=1.0,
        index_version="mock-index-v1",
        corpus_version="mock-corpus-v1",
        rerank_config_version="mock-rerank-v1",
    )


def test_r0_r1_r2_r3_share_one_pool_and_execute_distinct_stages() -> None:
    chunks = (
        _chunk("C1", "alpha treatment evidence", (1.0, 0.0)),
        _chunk("C2", "beta treatment evidence", (0.8, 0.2)),
        _chunk("C3", "gamma background", (0.0, 1.0)),
    )
    bm25 = CountingSearch("bm25", chunks)
    vector = CountingSearch("vector", tuple(reversed(chunks)))
    model = FakeCrossEncoder()
    service = RetrievalService(
        bm25,
        vector,  # type: ignore[arg-type]
        lambda _query: (1.0, 0.0),
        _config(),
        cross_encoder=CrossEncoderScorer(
            model_factory=lambda _name: model,
            alpha=1.0,
            score_semantics="probability",
        ),
        support_gate=KeepAllGate(),
    )
    query = Query(query_id="MOCK-Q1", text="treatment evidence")
    pool = service.retrieve_initial_pool(query)

    results = {
        condition: service.search_from_pool(query, pool, condition)
        for condition in RetrievalCondition
    }

    assert bm25.calls == 1 and vector.calls == 1
    assert {result.initial_candidate_pool_hash for result in results.values()} == {pool.pool_hash}
    assert "feature_rerank" not in results[RetrievalCondition.R0].stage_trace
    assert "mmr" not in results[RetrievalCondition.R0].stage_trace
    assert "feature_rerank" in results[RetrievalCondition.R1].stage_trace
    assert "cross_encoder" in results[RetrievalCondition.R2].stage_trace
    assert "claim_evidence_support_gate" in results[RetrievalCondition.R3].stage_trace
    assert model.calls == 2  # exactly R2 and R3
    assert results[RetrievalCondition.R1].selected_chunks != results[RetrievalCondition.R2].selected_chunks


def test_r3_all_removed_is_empty_and_never_restores_best_candidate() -> None:
    chunk = _chunk("C1", "alpha", (1.0, 0.0))
    service = RetrievalService(
        CountingSearch("bm25", (chunk,)),
        CountingSearch("vector", (chunk,)),  # type: ignore[arg-type]
        lambda _query: (1.0, 0.0),
        _config(),
        cross_encoder=CrossEncoderScorer(
            model_factory=lambda _name: FakeCrossEncoder(),
            alpha=1.0,
            score_semantics="probability",
        ),
        support_gate=RemoveAllGate(),
    )
    query = Query(query_id="MOCK-Q2", text="alpha")

    result = service.search_from_pool(query, service.retrieve_initial_pool(query), RetrievalCondition.R3)

    assert result.status is SearchStatus.EMPTY
    assert result.selected_chunks == ()
    assert not any(log.selected for log in result.rank_log)


def test_a4_ranking_scores_are_not_gate2_quality_without_explicit_scorer() -> None:
    chunk = _chunk("C1", "alpha", (1.0, 0.0))
    query = Query(query_id="MOCK-Q3", text="alpha")
    service = RetrievalService(
        CountingSearch("bm25", (chunk,)), None, None, _config()
    )

    result = service.search_from_pool(query, service.retrieve_initial_pool(query), RetrievalCondition.R1)

    assert result.ranking_score_kind == "RANKING"
    assert result.ranking_score_scope == "QUERY_LOCAL"
    assert result.ranking_score_calibrated is False
    assert result.quality_scores == {}
    assert result.quality_score_kind == "UNKNOWN"


def test_explicit_quality_port_is_the_only_gate2_eligible_score_source() -> None:
    chunk = _chunk("C1", "alpha", (1.0, 0.0))
    query = Query(query_id="MOCK-Q4", text="alpha")
    service = RetrievalService(
        CountingSearch("bm25", (chunk,)), None, None, _config(), quality_scorer=FixedQualityScorer()
    )

    result = service.search_from_pool(query, service.retrieve_initial_pool(query), RetrievalCondition.R1)

    assert result.quality_scores == {"C1": 0.8}
    assert result.quality_score_kind == "QUALITY"
    assert result.quality_score_scope == "CROSS_QUERY"
    assert result.quality_score_calibrated is True


def _a3_hit(channel: str, *, index_version: str = "mock-index-v1") -> dict[str, object]:
    return {
        "document_kind": "evidence",
        "channel": channel,
        "rank": 1,
        "raw_score": 2.5 if channel == "lexical" else None,
        "distance": 0.2 if channel == "vector" else None,
        "chunk_id": "C-A3-1",
        "evidence_id": "MOCK-EVIDENCE-A3-1",
        "title": "Mock A3 evidence",
        "text": "Mock span text.",
        "source_type": "mock_fixture",
        "evidence_level": "mock_level",
        "population": "mock population",
        "intervention": None,
        "comparator": None,
        "outcome": "mock outcome",
        "published_at": "2025-01-01T00:00:00Z",
        "page": 1,
        "raw_page": "1",
        "section": "mock section",
        "mock": True,
        "tombstone": False,
        "live_state": "live",
        "chunk_content_hash": "mock-chunk-hash",
        "evidence_content_hash": "mock-evidence-hash",
        "span_refs": [{
            "span_id": "MOCK-SPAN-1",
            "chunk_id": "C-A3-1",
            "text": "Mock span text.",
            "char_start": 0,
            "char_end": 15,
            "offset_scope": "chunk",
            "document_char_start": 0,
            "document_char_end": 15,
            "page": 1,
            "raw_page": "1",
            "section": "mock section",
            "span_content_hash": "mock-span-hash",
            "chunk_content_hash": "mock-chunk-hash",
            "evidence_content_hash": "mock-evidence-hash",
        }],
        "corpus_version": "mock-corpus-v1",
        "index_version": index_version,
        "chunk_policy_version": "mock-chunk-policy-v1",
        "embedding_provider": "mock",
        "embedding_model": "upstream:MOCK-A3-EMBEDDING",
        "embedding_revision": "fixture-v1",
        "embedding_source_kind": "fixture",
        "wiki_builder_version": "mock-wiki-v1",
        "config_schema_version": "mock-config-v1",
        "metadata": {"stable_id": "upstream:MOCK-A3-EVIDENCE-1"},
    }


def test_a3_search_hits_build_versioned_pool_and_preserve_real_span_refs() -> None:
    query = Query(query_id="MOCK-Q5", text="mock evidence")

    pool = build_initial_pool_from_a3_hits(
        query,
        [_a3_hit("lexical")],
        [_a3_hit("vector")],
        _config(),
        content_vectors={"C-A3-1": (1.0, 0.0)},
    )

    chunk = pool.fused_candidates[0].chunk
    assert chunk.mock is True
    assert chunk.span_refs[0]["span_id"] == "MOCK-SPAN-1"
    assert chunk.embedding_model == "upstream:MOCK-A3-EMBEDDING"
    assert pool.index_version == "mock-index-v1"


def test_a3_pool_adapter_rejects_mixed_index_versions() -> None:
    with pytest.raises(ValueError, match="version mismatch"):
        build_initial_pool_from_a3_hits(
            Query(query_id="MOCK-Q6", text="mock evidence"),
            [_a3_hit("lexical")],
            [_a3_hit("vector", index_version="other-index")],
            _config(),
        )
