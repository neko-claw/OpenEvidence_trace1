"""Tests for the extended 10-feature candidate computation (4.2)."""

from __future__ import annotations

import pytest

from retrieval.config import RetrievalConfig
from retrieval.models import Candidate, EvidenceChunk, Query
from retrieval.rerank import FeatureReranker


def _chunk(chunk_id: str, **changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": chunk_id,
        "evidence_id": f"evidence-{chunk_id}",
        "stable_id": f"upstream:MOCK-A4-{chunk_id}",
        "text": "Clinical evidence snippet.",
        "source_type": "pubmed",
        "url": "",
        "mock": True,
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


def _candidate(chunk_id: str, **changes: object) -> Candidate:
    values: dict[str, object] = {"chunk": _chunk(chunk_id), "rrf_score": 0.02}
    values.update(changes)
    return Candidate(**values)  # type: ignore[arg-type]


def test_rank_logs_all_ten_features() -> None:
    query = Query(query_id="q1", text="amlodipine hypertension trial")
    ranks = FeatureReranker(RetrievalConfig()).rank(
        query,
        [
            _candidate("c1", bm25_raw_score=2.0, vector_raw_score=0.8),
            _candidate("c2", bm25_raw_score=1.0, vector_raw_score=0.5),
        ],
    )

    features = ranks[0].candidate.feature_scores
    for name in (
        "semantic",
        "lexical",
        "rrf",
        "title_abstract",
        "pico_match",
        "evidence_level",
        "freshness",
        "source_reliability",
        "source_quality",
        "fulltext",
        "redundancy",
    ):
        assert name in features, name


def test_title_abstract_feature_measures_token_overlap() -> None:
    query = Query(query_id="q1", text="amlodipine hypertension")
    ranks = FeatureReranker(RetrievalConfig()).rank(
        query,
        [
            _candidate("match", chunk=_chunk("match", title="Amlodipine for hypertension", text="randomized trial")),
            _candidate("no-match", chunk=_chunk("no-match", title="Unrelated topic", text="another snippet")),
        ],
    )

    by_id = {log.candidate.chunk.chunk_id: log for log in ranks}
    assert by_id["match"].candidate.feature_scores["title_abstract"] > 0.0
    assert by_id["no-match"].candidate.feature_scores["title_abstract"] == 0.0


def test_source_quality_uses_source_type_table() -> None:
    query = Query(query_id="q1", text="hypertension")
    ranks = FeatureReranker(RetrievalConfig()).rank(
        query,
        [
            _candidate("guide", chunk=_chunk("guide", source_type="guideline")),
            _candidate("pubmed", chunk=_chunk("pubmed", source_type="pubmed")),
            _candidate("other", chunk=_chunk("other", source_type="mystery")),
        ],
    )

    by_id = {log.candidate.chunk.chunk_id: log for log in ranks}
    assert by_id["guide"].candidate.feature_scores["source_quality"] == pytest.approx(1.0)
    assert by_id["pubmed"].candidate.feature_scores["source_quality"] == pytest.approx(0.9)
    assert by_id["other"].candidate.feature_scores["source_quality"] == pytest.approx(0.5)


def test_fulltext_feature_prefers_long_text_and_europepmc() -> None:
    query = Query(query_id="q1", text="hypertension")
    ranks = FeatureReranker(RetrievalConfig()).rank(
        query,
        [
            _candidate("abstract", chunk=_chunk("abstract", text="short")),
            _candidate("fulltext", chunk=_chunk("fulltext", text="word " * 800)),
            _candidate("europe", chunk=_chunk("europe", source_type="europepmc", text="short")),
        ],
    )

    by_id = {log.candidate.chunk.chunk_id: log for log in ranks}
    assert by_id["abstract"].candidate.feature_scores["fulltext"] == pytest.approx(0.5)
    assert by_id["fulltext"].candidate.feature_scores["fulltext"] == pytest.approx(1.0)
    assert by_id["europe"].candidate.feature_scores["fulltext"] == pytest.approx(1.0)


def test_redundancy_feature_is_diagnostic_only_and_mmr_owns_dedup() -> None:
    """6.6: 冗余惩罚不应提前塞入静态 feature_score，MMR 是唯一的去冗余环节。

    The ``redundancy`` feature stays in the audit trail as diagnostics, but it
    must not depress the static rerank score: identical raw scores keep their
    tie order (by chunk_id) and de-duplication happens in ``select_mmr`` via
    the ``(1 - lambda) * max_similarity`` penalty.
    """
    query = Query(query_id="q1", text="hypertension trial")
    first = _candidate(
        "first",
        chunk=_chunk("first", content_vector=(1.0, 0.0)),
        bm25_raw_score=2.0,
        vector_raw_score=0.9,
    )
    duplicate = _candidate(
        "duplicate",
        chunk=_chunk("duplicate", content_vector=(0.999, 0.001)),
        bm25_raw_score=2.0,
        vector_raw_score=0.9,
    )
    diverse = _candidate(
        "diverse",
        chunk=_chunk("diverse", content_vector=(0.0, 1.0)),
        bm25_raw_score=2.0,
        vector_raw_score=0.9,
    )

    ranks = FeatureReranker(RetrievalConfig()).rank(query, [first, duplicate, diverse])

    by_id = {log.candidate.chunk.chunk_id: log for log in ranks}
    assert by_id["duplicate"].candidate.feature_scores["redundancy"] > 0.9
    assert by_id["diverse"].candidate.feature_scores["redundancy"] == pytest.approx(0.0, abs=0.01)
    # 静态重排分数不再被冗余惩罚压低：同分候选保持 rrf 并列顺序（chunk_id 稳定序）。
    assert by_id["diverse"].candidate.rerank_score == pytest.approx(by_id["duplicate"].candidate.rerank_score)
    assert by_id["first"].candidate.rerank_score == pytest.approx(by_id["duplicate"].candidate.rerank_score)


def test_mmr_applies_similarity_penalty_as_the_only_redundancy_control() -> None:
    """MMR 用 (1-lambda)*max_similarity 去冗余，硬上限 2 chunk/文献、4 chunk/来源。"""
    from retrieval.models import RankLog
    from retrieval.rerank import select_mmr

    query = Query(query_id="q1", text="hypertension trial")
    first = _candidate(
        "first",
        chunk=_chunk("first", content_vector=(1.0, 0.0)),
        bm25_raw_score=2.0,
        vector_raw_score=0.9,
    )
    duplicate = _candidate(
        "duplicate",
        chunk=_chunk("duplicate", content_vector=(0.999, 0.001)),
        bm25_raw_score=2.0,
        vector_raw_score=0.9,
    )
    ranks = FeatureReranker(RetrievalConfig()).rank(query, [first, duplicate])

    config = RetrievalConfig(selection_top_k=2, mmr_lambda=0.75)
    selected = select_mmr(ranks, config, 2)

    # 两条都进入选择，但后选中的那条（与已选高度相似）记录了高 mmr_similarity_penalty。
    assert len(selected) == 2
    penalties = {
        log.candidate.chunk.chunk_id: log.candidate.feature_scores["mmr_similarity_penalty"]
        for log in selected
    }
    assert max(penalties.values()) > 0.9
    assert min(penalties.values()) == pytest.approx(0.0, abs=0.01)
    assert selected[0].candidate.feature_scores["mmr_score"] >= selected[1].candidate.feature_scores["mmr_score"]
