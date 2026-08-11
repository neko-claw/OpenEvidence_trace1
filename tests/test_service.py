from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from retrieval.bm25 import BM25Index
from retrieval.config import RetrievalConfig
from retrieval.models import EvidenceChunk, Query, ScoredChunk, SearchStatus
from retrieval.service import RetrievalService
from retrieval.vector import InMemoryVectorSearch


class _FailingSearch:
    def search(self, _value: object, _k: int) -> list[ScoredChunk]:
        raise RuntimeError("simulated channel outage")


class _StaticSearch:
    def __init__(self, results: Sequence[ScoredChunk]) -> None:
        self._results = list(results)

    def search(self, _value: object, _k: int) -> list[ScoredChunk]:
        return list(self._results)


class _SecretFailingSearch:
    def search(self, _value: object, _k: int) -> list[ScoredChunk]:
        raise RuntimeError("https://internal.example/retrieval?token=super-secret")


def _config() -> RetrievalConfig:
    return RetrievalConfig(
        bm25_top_k=3,
        vector_top_k=3,
        fusion_top_k=5,
        rerank_top_k=5,
        selection_top_k=2,
        index_version="index-20260811",
        corpus_version="corpus-20260811",
        rerank_config_version="rerank-20260811",
    )


def _indexed_chunks(evidence_chunks: tuple[EvidenceChunk, ...]) -> tuple[EvidenceChunk, ...]:
    return tuple(
        replace(chunk, index_version="index-20260811", corpus_version="corpus-20260811")
        for chunk in evidence_chunks
    )


def test_search_runs_full_pipeline_and_returns_selected_chunks_full_logs_versions_and_timings(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    chunks = _indexed_chunks(evidence_chunks)
    service = RetrievalService(
        BM25Index(chunks),
        InMemoryVectorSearch({
            chunks[0].chunk_id: (chunks[0], (1.0, 0.0)),
            chunks[1].chunk_id: (chunks[1], (0.8, 0.2)),
            chunks[2].chunk_id: (chunks[2], (0.0, 1.0)),
        }),
        lambda _query: (1.0, 0.0),
        _config(),
    )

    result = service.search(Query(query_id="q-full", text="amlodipine hypertension"))

    assert result.status is SearchStatus.OK
    assert result.index_version == "index-20260811"
    assert result.corpus_version == "corpus-20260811"
    assert result.rerank_config_version == "rerank-20260811"
    assert result.selected_chunks == tuple(
        log.candidate.chunk for log in result.rank_log if log.selected
    )
    assert len(result.rank_log) >= len(result.selected_chunks) > 0
    assert {"bm25", "vector", "fusion", "rerank", "mmr", "total"} <= set(result.stage_latency_ms)
    assert all(isinstance(value, int) and value >= 0 for value in result.stage_latency_ms.values())
    assert result.latency_ms == result.stage_latency_ms["total"]
    assert result.retrieval_warning is None or "single source" in result.retrieval_warning.casefold()


def test_search_appends_only_explicit_english_terms_to_bm25_query_and_preserves_query_for_vector_provider() -> None:
    english_evidence = EvidenceChunk(
        chunk_id="english-guideline",
        evidence_id="e-english-guideline",
        stable_id="PMID:english-guideline",
        text="Amlodipine treatment for hypertension in older adults.",
        source_type="pubmed",
        evidence_level="rct",
        index_version="index-20260811",
        corpus_version="corpus-20260811",
    )
    received_queries: list[Query] = []
    original_query = Query(
        query_id="q-chinese-english",
        text="老年高血压用药",
        english_terms=("amlodipine", "hypertension"),
    )
    service = RetrievalService(
        BM25Index((english_evidence,)),
        _StaticSearch([]),
        lambda query: received_queries.append(query) or (1.0,),
        _config(),
    )

    result = service.search(original_query)

    assert result.selected_chunks == (english_evidence,)
    assert received_queries == [original_query]


def test_search_fail_closed_filters_undated_or_old_candidates_before_rrf_for_current_queries() -> None:
    base = EvidenceChunk(
        chunk_id="recent",
        evidence_id="e-recent",
        stable_id="PMID:recent",
        text="Recent hypertension evidence.",
        source_type="pubmed",
        published_at="2024-08-12",
        index_version="index-20260811",
        corpus_version="corpus-20260811",
    )
    old = replace(base, chunk_id="old", evidence_id="e-old", stable_id="PMID:old", published_at="2010-01-01")
    undated = replace(base, chunk_id="undated", evidence_id="e-undated", stable_id="PMID:undated", published_at=None)
    lexical = _StaticSearch(
        [
            ScoredChunk(chunk=old, score=0.9, rank=1, stage="bm25"),
            ScoredChunk(chunk=undated, score=0.8, rank=2, stage="bm25"),
            ScoredChunk(chunk=base, score=0.7, rank=3, stage="bm25"),
        ]
    )
    service = RetrievalService(lexical, None, None, _config())

    result = service.search(Query(query_id="q-current", text="hypertension", freshness="current"))

    assert result.selected_chunks == (base,)
    assert [log.candidate.chunk.chunk_id for log in result.rank_log] == ["recent"]
    assert any("excluded 2" in reason for reason in result.degradation_reasons)


def test_search_does_not_apply_latest_window_to_generic_queries() -> None:
    old = EvidenceChunk(
        chunk_id="old-generic",
        evidence_id="e-old-generic",
        stable_id="PMID:old-generic",
        text="Older hypertension evidence.",
        source_type="pubmed",
        published_at="2010-01-01",
        index_version="index-20260811",
        corpus_version="corpus-20260811",
    )
    service = RetrievalService(
        _StaticSearch([ScoredChunk(chunk=old, score=0.9, rank=1, stage="bm25")]), None, None, _config()
    )

    result = service.search(Query(query_id="q-generic", text="hypertension"))

    assert result.selected_chunks == (old,)


def test_search_continues_bm25_only_when_vector_provider_fails(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    chunks = _indexed_chunks(evidence_chunks)
    service = RetrievalService(BM25Index(chunks), _FailingSearch(), lambda _query: (_ for _ in ()).throw(RuntimeError("embedding down")), _config())

    result = service.search(Query(query_id="q-vector-down", text="amlodipine"))

    assert result.status is SearchStatus.PARTIAL
    assert any("vector" in reason for reason in result.degradation_reasons)
    assert result.selected_chunks
    assert "partial" in result.retrieval_warning.casefold()
    assert result.stage_latency_ms["vector"] >= 0


def test_search_continues_vector_only_when_bm25_fails(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    chunk = _indexed_chunks(evidence_chunks)[0]
    vector = _StaticSearch([ScoredChunk(chunk=chunk, score=0.9, rank=1, stage="vector")])
    service = RetrievalService(_FailingSearch(), vector, lambda _query: (1.0, 0.0), _config())

    result = service.search(Query(query_id="q-bm25-down", text="amlodipine"))

    assert result.status is SearchStatus.PARTIAL
    assert any("bm25" in reason for reason in result.degradation_reasons)
    assert result.selected_chunks == (chunk,)


def test_search_returns_partial_not_empty_when_bm25_fails_but_vector_is_operational_and_empty(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    service = RetrievalService(_FailingSearch(), _StaticSearch([]), lambda _query: (1.0, 0.0), _config())

    result = service.search(Query(query_id="q-bm25-down-empty", text="amlodipine"))

    assert result.status is SearchStatus.PARTIAL
    assert result.selected_chunks == ()
    assert "partial" in result.retrieval_warning.casefold()
    assert any("bm25" in reason for reason in result.degradation_reasons)


def test_search_returns_failed_when_all_operational_channels_fail(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    service = RetrievalService(_FailingSearch(), _FailingSearch(), lambda _query: (1.0, 0.0), _config())

    result = service.search(Query(query_id="q-failed", text="amlodipine"))

    assert result.status is SearchStatus.FAILED
    assert result.corpus_version == "corpus-20260811"
    assert result.selected_chunks == ()
    assert result.rank_log == ()
    assert len(result.degradation_reasons) == 2
    assert "failed" in result.retrieval_warning.casefold()


def test_search_returns_empty_when_live_channels_produce_no_candidates(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    chunks = _indexed_chunks(evidence_chunks)
    service = RetrievalService(BM25Index(chunks), _StaticSearch([]), lambda _query: (1.0, 0.0), _config())

    result = service.search(Query(query_id="q-empty", text="unmatched term"))

    assert result.status is SearchStatus.EMPTY
    assert result.corpus_version == "corpus-20260811"
    assert result.selected_chunks == ()
    assert "empty" in result.retrieval_warning.casefold()
    assert result.degradation_reasons == ()


def test_search_warns_when_final_selection_is_from_one_source(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    first, second, _ = _indexed_chunks(evidence_chunks)
    first = replace(first, source_type="pubmed")
    second = replace(second, source_type="pubmed")
    service = RetrievalService(
        BM25Index((first, second)),
        None,
        None,
        _config(),
    )

    result = service.search(Query(query_id="q-one-source", text="hypertension"))

    assert result.status is SearchStatus.PARTIAL
    assert "single source" in result.retrieval_warning.casefold()


def test_search_excludes_tombstoned_or_wrong_version_candidates(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    live = _indexed_chunks(evidence_chunks)[0]
    stale = replace(live, chunk_id="stale", is_tombstoned=True)
    wrong_version = replace(live, chunk_id="wrong-version", index_version="other")
    vector = _StaticSearch(
        [
            ScoredChunk(chunk=live, score=0.9, rank=1, stage="vector"),
            ScoredChunk(chunk=stale, score=0.8, rank=2, stage="vector"),
            ScoredChunk(chunk=wrong_version, score=0.7, rank=3, stage="vector"),
        ]
    )
    service = RetrievalService(_FailingSearch(), vector, lambda _query: (1.0, 0.0), _config())

    result = service.search(Query(query_id="q-defensive", text="amlodipine"))

    assert result.status is SearchStatus.PARTIAL
    assert result.selected_chunks == (live,)


def test_search_excludes_a_candidate_mutated_after_contract_validation(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    live = _indexed_chunks(evidence_chunks)[0]
    malformed = replace(live, chunk_id="malformed")
    item = ScoredChunk(chunk=malformed, score=0.8, rank=2, stage="vector")
    object.__setattr__(malformed, "content_vector", ("not-a-number",))
    vector = _StaticSearch(
        [
            ScoredChunk(chunk=live, score=0.9, rank=1, stage="vector"),
            item,
        ]
    )
    service = RetrievalService(_FailingSearch(), vector, lambda _query: (1.0, 0.0), _config())

    result = service.search(Query(query_id="q-mutated-candidate", text="amlodipine"))

    assert result.status is SearchStatus.PARTIAL
    assert result.selected_chunks == (live,)
    assert any("excluded 1" in reason for reason in result.degradation_reasons)


def test_search_marks_candidate_corruption_as_partial_instead_of_silent_ok(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    chunks = _indexed_chunks(evidence_chunks)
    tombstoned = replace(chunks[0], is_tombstoned=True)
    vector = _StaticSearch([ScoredChunk(chunk=tombstoned, score=0.9, rank=1, stage="vector")])
    service = RetrievalService(BM25Index(chunks), vector, lambda _query: (1.0, 0.0), _config())

    result = service.search(Query(query_id="q-corrupt", text="amlodipine"))

    assert result.status is SearchStatus.PARTIAL
    assert "excluded" in result.retrieval_warning.casefold()


def test_search_retains_all_fused_candidates_in_audit_when_rerank_selection_is_capped(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    chunks = _indexed_chunks(evidence_chunks)
    config = replace(_config(), fusion_top_k=3, rerank_top_k=1, selection_top_k=1)
    vector = _StaticSearch(
        [
            ScoredChunk(chunk=chunk, score=1.0 - index / 10, rank=index, stage="vector")
            for index, chunk in enumerate(chunks, start=1)
        ]
    )
    service = RetrievalService(BM25Index(chunks), vector, lambda _query: (1.0, 0.0), config)

    result = service.search(Query(query_id="q-full-audit", text="hypertension"))

    assert len(result.rank_log) == 3
    assert {log.candidate.chunk.chunk_id for log in result.rank_log} == {chunk.chunk_id for chunk in chunks}
    assert [log.final_rank for log in result.rank_log] == [1, 2, 3]
    assert all(log.candidate.feature_scores for log in result.rank_log)
    assert [log.selected for log in result.rank_log] == [True, False, False]
    assert len(result.selected_chunks) == 1


def test_search_orders_selected_audit_rows_by_mmr_selection_rank(
    evidence_chunks: tuple[EvidenceChunk, ...],
) -> None:
    base = _indexed_chunks(evidence_chunks)[0]
    chunks = (
        replace(base, chunk_id="a", evidence_id="e-a", stable_id="PMID:a", content_vector=(1.0, 0.0)),
        replace(base, chunk_id="b", evidence_id="e-b", stable_id="PMID:b", content_vector=(0.99, 0.01)),
        replace(base, chunk_id="c", evidence_id="e-c", stable_id="PMID:c", content_vector=(0.0, 1.0)),
    )
    vector = _StaticSearch(
        [
            ScoredChunk(chunk=chunk, score=1.0 - index / 10, rank=index, stage="vector")
            for index, chunk in enumerate(chunks, start=1)
        ]
    )
    config = replace(_config(), rerank_top_k=3, selection_top_k=3, mmr_lambda=0.5)
    service = RetrievalService(_FailingSearch(), vector, lambda _query: (1.0, 0.0), config)

    result = service.search(Query(query_id="q-diverse-order", text="hypertension"))

    assert [chunk.chunk_id for chunk in result.selected_chunks] == ["a", "c", "b"]
    assert [log.candidate.chunk.chunk_id for log in result.rank_log if log.selected] == ["a", "c", "b"]
    assert [log.candidate.feature_scores["mmr_selection_rank"] for log in result.rank_log if log.selected] == [1.0, 2.0, 3.0]


def test_search_does_not_expose_raw_channel_exception_details(evidence_chunks: tuple[EvidenceChunk, ...]) -> None:
    chunks = _indexed_chunks(evidence_chunks)
    service = RetrievalService(BM25Index(chunks), _SecretFailingSearch(), lambda _query: (1.0, 0.0), _config())

    result = service.search(Query(query_id="q-no-secret", text="amlodipine"))

    rendered = " ".join((*result.degradation_reasons, result.retrieval_warning or ""))
    assert result.degradation_reasons == ("vector_unavailable",)
    assert "super-secret" not in rendered
    assert "internal.example" not in rendered
