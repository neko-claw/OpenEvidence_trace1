from __future__ import annotations

from math import isfinite

import pytest

import retrieval
from retrieval.config import RetrievalConfig
from retrieval.models import Candidate, EvidenceChunk, RankLog
from retrieval.rerank import select_mmr


def _chunk(chunk_id: str, **changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": chunk_id,
        "evidence_id": f"evidence-{chunk_id}",
        "stable_id": f"upstream:MOCK-A4-{chunk_id}",
        "text": "Clinical evidence snippet.",
        "source_type": "pubmed",
        "mock": True,
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


def _rank_log(
    chunk_id: str,
    *,
    score: float,
    rank: int,
    vector: tuple[float, ...] = (),
    **chunk_changes: object,
) -> RankLog:
    chunk = _chunk(chunk_id, content_vector=vector, **chunk_changes)
    candidate = Candidate(chunk=chunk, rrf_score=0.01, rerank_score=score, feature_scores={"semantic": score})
    return RankLog(
        candidate=candidate,
        feature_scores=candidate.feature_scores,
        final_rank=rank,
        selected=False,
        rerank_config_version="p0-v1",
    )


def test_select_mmr_is_available_from_the_retrieval_package() -> None:
    assert retrieval.select_mmr is select_mmr


def test_select_mmr_uses_similarity_penalty_to_choose_a_diverse_candidate() -> None:
    logs = (
        _rank_log("redundant-a", score=0.95, rank=1, vector=(1.0, 0.0)),
        _rank_log("redundant-b", score=0.93, rank=2, vector=(0.99, 0.01)),
        _rank_log("diverse", score=0.70, rank=3, vector=(0.0, 1.0)),
    )

    selected = select_mmr(logs, RetrievalConfig(mmr_lambda=0.5), k=2)

    assert [log.candidate.chunk.chunk_id for log in selected] == ["redundant-a", "diverse"]  # type: ignore[union-attr]
    assert selected[0].feature_scores["mmr_similarity_penalty"] == 0.0
    assert selected[1].feature_scores["mmr_similarity_penalty"] == 0.0
    assert selected[1].feature_scores["mmr_score"] == pytest.approx(0.35)


def test_select_mmr_prefers_eligible_guideline_systematic_review_and_rct_coverage_before_same_type_duplicates() -> None:
    logs = (
        _rank_log("rct-first", score=0.90, rank=1, evidence_level="rct"),
        _rank_log("rct-duplicate", score=0.90, rank=2, evidence_level="rct"),
        _rank_log("guideline", score=0.90, rank=3, evidence_level="guideline"),
        _rank_log("review", score=0.90, rank=4, evidence_level="systematic_review"),
    )

    selected = select_mmr(logs, RetrievalConfig(), k=3)

    assert [log.candidate.chunk.chunk_id for log in selected] == ["rct-first", "guideline", "review"]  # type: ignore[union-attr]
    assert [log.feature_scores["mmr_evidence_type_diversity_bonus"] for log in selected] == [0.03, 0.03, 0.03]


def test_select_mmr_never_rewards_an_anti_correlated_vector() -> None:
    logs = (
        _rank_log("first", score=0.9, rank=1, vector=(1.0, 0.0)),
        _rank_log("anti-correlated", score=0.5, rank=2, vector=(-1.0, 0.0)),
        _rank_log("orthogonal", score=0.7, rank=3, vector=(0.0, 1.0)),
    )

    selected = select_mmr(logs, RetrievalConfig(mmr_lambda=0.5), k=3)

    assert [log.candidate.chunk.chunk_id for log in selected] == ["first", "orthogonal", "anti-correlated"]  # type: ignore[union-attr]
    assert all(log.feature_scores["mmr_similarity_penalty"] >= 0.0 for log in selected)


def test_select_mmr_enforces_document_and_source_caps() -> None:
    logs = (
        _rank_log("doc-first", score=0.95, rank=1, evidence_id="same-document", stable_id="upstream:MOCK-A4-SHARED", source_type="pubmed"),
        _rank_log("doc-second", score=0.94, rank=2, evidence_id="same-document", stable_id="upstream:MOCK-A4-SHARED", source_type="pubmed"),
        _rank_log("pubmed-second", score=0.93, rank=3, source_type="PubMed"),
        _rank_log("pubmed-third", score=0.92, rank=4, source_type="pubmed"),
        _rank_log("guideline", score=0.91, rank=5, source_type="guideline"),
    )

    selected = select_mmr(
        logs,
        RetrievalConfig(max_chunks_per_document=1, max_chunks_per_source=2),
        k=4,
    )

    assert [log.candidate.chunk.chunk_id for log in selected] == ["doc-first", "pubmed-second", "guideline"]  # type: ignore[union-attr]


def test_select_mmr_document_cap_uses_stable_id_across_distinct_evidence_records() -> None:
    logs = (
        _rank_log("first-source", score=0.95, rank=1, evidence_id="evidence-a", stable_id="upstream:MOCK-A4-SHARED", source_type="pubmed"),
        _rank_log("second-source", score=0.94, rank=2, evidence_id="evidence-b", stable_id="upstream:MOCK-A4-SHARED", source_type="guideline"),
        _rank_log("independent", score=0.93, rank=3, evidence_id="evidence-c", stable_id="upstream:MOCK-A4-INDEPENDENT", source_type="guideline"),
    )

    selected = select_mmr(
        logs,
        RetrievalConfig(max_chunks_per_document=1, max_chunks_per_source=2),
        k=3,
    )

    assert [log.candidate.chunk.chunk_id for log in selected] == ["first-source", "independent"]  # type: ignore[union-attr]


def test_select_mmr_rejects_a_request_above_the_configured_context_budget() -> None:
    with pytest.raises(ValueError, match="selection_top_k"):
        select_mmr(
            (_rank_log("valid", score=0.7, rank=1),),
            RetrievalConfig(selection_top_k=1),
            k=3,
        )


def test_select_mmr_uses_rerank_final_rank_for_deterministic_ties() -> None:
    logs = (
        _rank_log("second-in-input", score=0.8, rank=2),
        _rank_log("first-in-rerank", score=0.8, rank=1),
    )

    selected = select_mmr(logs, RetrievalConfig(), k=2)

    assert [log.candidate.chunk.chunk_id for log in selected] == ["first-in-rerank", "second-in-input"]  # type: ignore[union-attr]
    assert [log.final_rank for log in selected] == [1, 2]
    assert all(log.selected for log in selected)
    assert all(log.feature_scores == log.candidate.feature_scores for log in selected)  # type: ignore[union-attr]


def test_select_mmr_treats_absent_vectors_as_zero_similarity() -> None:
    logs = (
        _rank_log("high", score=0.9, rank=1),
        _rank_log("lower", score=0.8, rank=2),
    )

    selected = select_mmr(logs, RetrievalConfig(mmr_lambda=0.5), k=2)

    assert [log.candidate.chunk.chunk_id for log in selected] == ["high", "lower"]  # type: ignore[union-attr]
    assert [log.feature_scores["mmr_similarity_penalty"] for log in selected] == [0.0, 0.0]


def test_select_mmr_treats_mutated_invalid_vectors_as_zero_similarity() -> None:
    high = _rank_log("high", score=0.9, rank=1)
    invalid = _rank_log("invalid", score=0.8, rank=2)
    object.__setattr__(invalid.candidate.chunk, "content_vector", (10**10000,))  # type: ignore[union-attr]

    selected = select_mmr((high, invalid), RetrievalConfig(mmr_lambda=0.5), k=2)

    assert [log.feature_scores["mmr_similarity_penalty"] for log in selected] == [0.0, 0.0]


def test_select_mmr_handles_zero_and_large_vectors_without_overflow() -> None:
    logs = (
        _rank_log("large-a", score=0.9, rank=1, vector=(1e308, 1e308)),
        _rank_log("large-b", score=0.8, rank=2, vector=(1e308, 0.0)),
        _rank_log("zero", score=0.7, rank=3, vector=(0.0, 0.0)),
    )

    selected = select_mmr(logs, RetrievalConfig(mmr_lambda=0.5), k=3)

    assert len(selected) == 3
    assert all(isfinite(float(log.feature_scores["mmr_score"])) for log in selected)
    zero_log = next(log for log in selected if log.candidate.chunk.chunk_id == "zero")  # type: ignore[union-attr]
    assert zero_log.feature_scores["mmr_similarity_penalty"] == 0.0


def test_select_mmr_filters_tombstoned_and_invalid_stable_ids() -> None:
    valid = _rank_log("valid", score=0.7, rank=4)
    tombstoned = _rank_log("tombstoned", score=0.99, rank=1, is_tombstoned=True)
    malformed_tombstone = _rank_log("malformed-tombstone", score=0.985, rank=2)
    invalid_stable = _rank_log("invalid-stable", score=0.98, rank=3)
    object.__setattr__(malformed_tombstone.candidate.chunk, "is_tombstoned", "true")  # type: ignore[union-attr]
    object.__setattr__(invalid_stable.candidate.chunk, "stable_id", " ")  # type: ignore[union-attr]

    selected = select_mmr((tombstoned, malformed_tombstone, invalid_stable, valid), RetrievalConfig(), k=3)

    assert [log.candidate.chunk.chunk_id for log in selected] == ["valid"]  # type: ignore[union-attr]


@pytest.mark.parametrize("k", [0, -1, True, 1.5])
def test_select_mmr_rejects_invalid_k(k: object) -> None:
    with pytest.raises(ValueError, match="k"):
        select_mmr((_rank_log("valid", score=0.7, rank=1),), RetrievalConfig(), k=k)  # type: ignore[arg-type]


def test_select_mmr_rejects_duplicate_rank_logs() -> None:
    logs = (
        _rank_log("duplicate", score=0.9, rank=1),
        _rank_log("duplicate", score=0.8, rank=2),
    )

    with pytest.raises(ValueError, match="duplicate"):
        select_mmr(logs, RetrievalConfig(), k=2)
