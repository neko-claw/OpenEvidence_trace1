"""Tests for the six gap-closing additions: chunk fields, citation precision,
per-type curves, frozen guard, alpha in config, and per-type freshness weight."""

from __future__ import annotations

import json

import pytest

from retrieval.ablation import AblationRow
from retrieval.config import RetrievalConfig
from retrieval.cross_encoder import CrossEncoderScorer
from retrieval.evaluation import citation_proxy_precision, context_tokens
from retrieval.models import EvidenceChunk, Query
from retrieval.rerank import FeatureReranker
from retrieval.store import EvidenceStore
from retrieval.models import RetrievalAlignmentHint
from retrieval.tuning import (
    grid_details,
    recall_curve_by_type,
    require_frozen,
    verify_frozen,
    write_freeze_record,
    write_grid_details_csv,
)
from retrieval.models import Candidate


def _chunk(chunk_id: str, **changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": chunk_id,
        "evidence_id": f"evidence-{chunk_id}",
        "stable_id": f"upstream:MOCK-A4-{chunk_id}",
        "text": "Clinical evidence snippet.",
        "source_type": "pubmed",
        "evidence_level": "rct",
        "index_version": "idx-t",
        "corpus_version": "corpus-t",
        "mock": True,
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


# --- Gap 1: page / section / token_count on chunks and the store ---


def test_chunk_carries_page_section_and_token_count() -> None:
    chunk = _chunk("c1", page="12-13", section="3.2 治疗", token_count=87)

    assert chunk.page == "12-13"
    assert chunk.section == "3.2 治疗"
    assert chunk.token_count == 87


def test_store_round_trips_page_section_and_token_count(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "e.db", index_version="idx-t", corpus_version="corpus-t")
    store.upsert_chunks((_chunk("c1", page="12", section="treatment", token_count=0),))

    loaded = store.load_chunks()

    assert loaded[0].page == "12"
    assert loaded[0].section == "treatment"
    assert loaded[0].token_count > 0  # auto-estimated on upsert when unset


def test_chunk_rejects_negative_token_count() -> None:
    with pytest.raises(ValueError, match="token_count"):
        _chunk("c1", token_count=-1)


def test_context_tokens_prefers_annotated_token_count() -> None:
    chunk = _chunk("c1", token_count=99)
    assert context_tokens((chunk,)) == 99


# --- Gap 2: citation_precision ---


def test_citation_proxy_precision_measures_aligned_citations_share() -> None:
    supports = (
        RetrievalAlignmentHint(claim_index=0, claim_text="a", decision="ALIGNED", evidence_ids=("e1", "e2")),
        RetrievalAlignmentHint(claim_index=1, claim_text="b", decision="INSUFFICIENT", evidence_ids=("e3",)),
    )

    assert citation_proxy_precision(supports) == pytest.approx(2 / 3)


def test_citation_proxy_precision_is_zero_without_citations() -> None:
    supports = (RetrievalAlignmentHint(claim_index=0, claim_text="a", decision="INSUFFICIENT", evidence_ids=()),)
    assert citation_proxy_precision(supports) == 0.0


def test_ablation_row_includes_citation_proxy_precision() -> None:
    row = AblationRow(
        condition="R1", recall_at_k0=0.0, ndcg_at_k1=0.0, mrr=0.0, source_diversity=0.0,
        duplicate_rate=0.0, citation_proxy_precision=0.9, citation_proxy_coverage=0.8,
        claim_alignment_proxy_rate=0.7, conflict_rate=0.0, context_tokens=0,
        estimated_cost_usd=0.0, latency_ms=0.0,
    )
    assert row.citation_proxy_precision == 0.9


# --- Gap 3: per-question details and per-type recall curves ---


def _questions() -> list[tuple[Query, dict[str, float]]]:
    return [
        (
            Query(query_id="q1", text="amlodipine hypertension", question_type="therapy"),
            {"c-amlodipine": 3.0},
        ),
        (
            Query(query_id="q2", text="latest hypertension trial", question_type="latest_trial"),
            {"c-amlodipine": 3.0},
        ),
    ]


CHUNKS = (
    _chunk("c-amlodipine", title="Amlodipine", text="Amlodipine reduced blood pressure in older adults."),
    _chunk("c-other", title="Statins", text="Statins lower LDL cholesterol."),
)


def test_grid_details_returns_per_question_rows(tmp_path) -> None:
    details = grid_details(
        _questions(), CHUNKS, k0_values=(20,), k1_values=(10,), k2_values=(3,), config=_config()
    )

    assert len(details) == 2  # two questions, one K triple
    assert {row.question_id for row in details} == {"q1", "q2"}
    assert {row.question_type for row in details} == {"therapy", "latest_trial"}
    assert all(row.k2 <= row.k1 for row in details)

    path = write_grid_details_csv(tmp_path / "details.csv", details)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("k0,k1,k2,question_id,question_type")
    assert len(lines) == 1 + len(details)


def test_recall_curve_by_type_groups_question_types() -> None:
    curves = recall_curve_by_type(_questions(), CHUNKS, k0_values=(20, 80), k1=10, k2=3, config=_config())

    assert set(curves) == {"therapy", "latest_trial"}
    assert len(curves["therapy"]) == 2
    assert {row.k0 for row in curves["latest_trial"]} == {20, 80}


def _config() -> RetrievalConfig:
    return RetrievalConfig(
        index_version="idx-t", corpus_version="corpus-t", rerank_config_version="rerank-t"
    )


# --- Gap 4: frozen guard ---


def _grid_row() -> object:
    from retrieval.tuning import run_grid

    return run_grid(_questions(), CHUNKS, k0_values=(20,), k1_values=(10,), k2_values=(3,), config=_config())[0]


def test_verify_frozen_accepts_matching_config(tmp_path) -> None:
    row = _grid_row()
    config = _frozen_config(row)
    path = write_freeze_record(tmp_path / "freeze.json", chosen=row, config=config, dev_summary={})

    assert verify_frozen(path, config) is True


def _frozen_config(row: object) -> RetrievalConfig:
    return RetrievalConfig(
        index_version="idx-t",
        corpus_version="corpus-t",
        rerank_config_version="rerank-t",
        fusion_top_k=row.k0,  # type: ignore[attr-defined]
        rerank_top_k=row.k1,  # type: ignore[attr-defined]
        selection_top_k=row.k2,  # type: ignore[attr-defined]
    )


def test_require_frozen_rejects_drifted_config(tmp_path) -> None:
    row = _grid_row()
    path = write_freeze_record(tmp_path / "freeze.json", chosen=row, config=_config(), dev_summary={})
    drifted = RetrievalConfig(
        index_version="idx-t", corpus_version="corpus-t", rerank_config_version="rerank-t",
        mmr_lambda=0.99,
    )

    assert verify_frozen(path, drifted) is False
    with pytest.raises(ValueError, match="not frozen"):
        require_frozen(path, drifted)


# --- Gap 5: alpha lives in the config / freeze record ---


def test_cross_encoder_alpha_is_in_config_and_freeze_record(tmp_path) -> None:
    row = _grid_row()
    config = RetrievalConfig(
        cross_encoder_alpha=0.6,
        fusion_top_k=row.k0,  # type: ignore[attr-defined]
        rerank_top_k=row.k1,  # type: ignore[attr-defined]
        selection_top_k=row.k2,  # type: ignore[attr-defined]
    )
    path = write_freeze_record(tmp_path / "freeze.json", chosen=row, config=config, dev_summary={})

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["config"]["cross_encoder_alpha"] == 0.6
    assert verify_frozen(path, config) is True


def test_cross_encoder_scorer_alpha_defaults_from_config() -> None:
    scorer = CrossEncoderScorer(model_factory=lambda name: object())
    assert scorer.alpha == 0.5  # matches RetrievalConfig.cross_encoder_alpha default


# --- Gap 6: per-type freshness weight ---


def _candidate(chunk_id: str, published_at: str) -> Candidate:
    chunk = _chunk(chunk_id, published_at=published_at, evidence_level="rct")
    return Candidate(chunk=chunk, rrf_score=0.01, bm25_raw_score=1.0, vector_raw_score=0.5)


def test_latest_trial_question_raises_freshness_weight() -> None:
    older = _candidate("older", "2018-01-01")
    newer = _candidate("newer", "2025-01-01")
    query = Query(
        query_id="q1",
        text="latest hypertension trial",
        question_type="latest_trial",
        freshness="latest",
    )

    ranks = FeatureReranker(RetrievalConfig()).rank(query, [older, newer])

    by_id = {log.candidate.chunk.chunk_id: log for log in ranks}
    assert by_id["newer"].candidate.rerank_score > by_id["older"].candidate.rerank_score
    # With freshness weight raised to 0.20 the gap widens vs the base 0.10.
    base = FeatureReranker(RetrievalConfig()).rank(
        Query(
            query_id="q2",
            text="latest hypertension evidence",  # latest term but not a trial question
            question_type="generic",
            freshness="latest",
        ),
        [older, newer],
    )
    base_by_id = {log.candidate.chunk.chunk_id: log for log in base}
    gap_raised = by_id["newer"].candidate.rerank_score - by_id["older"].candidate.rerank_score
    gap_base = base_by_id["newer"].candidate.rerank_score - base_by_id["older"].candidate.rerank_score
    assert gap_raised > gap_base
