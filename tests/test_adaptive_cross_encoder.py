"""Tests for Cross-Encoder adapter (P1) and adaptive K rules (4.3.4)."""

from __future__ import annotations

import math

import pytest

from retrieval.adaptive import adapt_k
from retrieval.config import RetrievalConfig
from retrieval.cross_encoder import CrossEncoderError, CrossEncoderScorer
from retrieval.models import Candidate, EvidenceChunk, Query


class FakeCrossEncoder:
    def __init__(self, scores: list[float]) -> None:
        self._scores = scores
        self.predict_calls: list[list[tuple[str, str]]] = []

    def predict(self, pairs: object) -> list[float]:
        self.predict_calls.append(list(pairs))  # type: ignore[arg-type]
        return list(self._scores)


def _chunk(chunk_id: str) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        evidence_id=f"evidence-{chunk_id}",
        stable_id=f"PMID:{chunk_id}",
        text="Clinical evidence snippet.",
        source_type="pubmed",
        evidence_level="rct",
    )


def _candidate(chunk_id: str, rerank_score: float) -> Candidate:
    return Candidate(chunk=_chunk(chunk_id), rrf_score=0.01, rerank_score=rerank_score)


def _query(**changes: object) -> Query:
    values: dict[str, object] = {"query_id": "q1", "text": "老年高血压治疗"}
    values.update(changes)
    return Query(**values)  # type: ignore[arg-type]


def test_cross_encoder_loads_lazily_and_blends_scores() -> None:
    calls: list[str] = []

    def factory(name: str) -> FakeCrossEncoder:
        calls.append(name)
        return FakeCrossEncoder([0.9, 0.5])

    scorer = CrossEncoderScorer(model_name="reranker", model_factory=factory)
    assert calls == []

    candidates = scorer.score(_query(), [_candidate("c1", 0.6), _candidate("c2", 0.6)])

    assert calls == ["reranker"]
    assert candidates[0].feature_scores["cross_encoder_score"] == pytest.approx(0.9)
    assert candidates[0].feature_scores["s_final"] == pytest.approx(0.5 * 0.9 + 0.5 * 0.6)
    assert candidates[0].feature_scores["s_final"] > candidates[1].feature_scores["s_final"]


def test_cross_encoder_orders_by_blended_score() -> None:
    scorer = CrossEncoderScorer(model_factory=lambda name: FakeCrossEncoder([0.2, 0.95]))

    ranked = scorer.score(_query(), [_candidate("a", 0.9), _candidate("b", 0.5)])

    assert [c.chunk.chunk_id for c in ranked] == ["b", "a"]


def test_cross_encoder_raises_stable_error_on_load_failure() -> None:
    def factory(name: str) -> FakeCrossEncoder:
        raise RuntimeError("no weights")

    scorer = CrossEncoderScorer(model_factory=factory)

    with pytest.raises(CrossEncoderError, match="cross_encoder"):
        scorer.score(_query(), [_candidate("c1", 0.5)])


def test_cross_encoder_rejects_nonfinite_scores() -> None:
    scorer = CrossEncoderScorer(model_factory=lambda name: FakeCrossEncoder([math.nan]))

    with pytest.raises(CrossEncoderError, match="finite"):
        scorer.score(_query(), [_candidate("c1", 0.5)])


def test_adapt_k_shrinks_for_precise_guideline_questions() -> None:
    query = _query(question_type="guideline", freshness="current", text="指南推荐")
    k1, k2, actions = adapt_k(query, RetrievalConfig())

    assert (k1, k2) == (10, 3)


def test_adapt_k_expands_for_multi_pico_questions() -> None:
    query = _query(
        question_type="therapy",
        pico_population=("older adults",),
        pico_intervention=("amlodipine",),
        pico_outcome=("blood pressure",),
        text="老年患者使用氨氯地平对血压的影响",
    )
    k1, k2, actions = adapt_k(query, RetrievalConfig())

    assert (k1, k2) == (30, 8)


def test_adapt_k_shrinks_for_latest_trial_questions() -> None:
    query = _query(question_type="latest_trial", freshness="latest", text="最新试验")
    k1, k2, actions = adapt_k(query, RetrievalConfig())

    assert (k1, k2) == (20, 5)


def test_adapt_k_keeps_defaults_for_generic_questions() -> None:
    query = _query(question_type="generic", freshness="generic", text="一般问题")
    k1, k2, actions = adapt_k(query, RetrievalConfig())

    # selection_top_k 默认 8，与冻结 config/retrieval-p0-v1.yaml 一致（round2 P2 修复）。
    assert (k1, k2) == (25, 8)
