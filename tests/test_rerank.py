from __future__ import annotations

from datetime import date

import pytest

from retrieval.config import RetrievalConfig
from retrieval.models import Candidate, EvidenceChunk, Query
from retrieval.rerank import FeatureReranker


def _chunk(chunk_id: str, **changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": chunk_id,
        "evidence_id": f"evidence-{chunk_id}",
        "stable_id": f"PMID:{chunk_id}",
        "text": "Clinical evidence snippet.",
        "source_type": "pubmed",
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{chunk_id}/",
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


def _candidate(chunk_id: str, **changes: object) -> Candidate:
    values: dict[str, object] = {"chunk": _chunk(chunk_id), "rrf_score": 0.02}
    values.update(changes)
    return Candidate(**values)  # type: ignore[arg-type]


def test_rank_promotes_pico_matched_guideline_for_therapy_query() -> None:
    query = Query(
        query_id="q-therapy",
        text="Treatment for older adults with hypertension",
        pico_population=("OLDER adults",),
        pico_intervention=("amlodipine",),
    )
    candidates = [
        _candidate(
            "rct-no-pico",
            chunk=_chunk("rct-no-pico", evidence_level="rct"),
            bm25_raw_score=1.0,
            vector_raw_score=0.1,
        ),
        _candidate(
            "guideline-pico",
            chunk=_chunk(
                "guideline-pico",
                evidence_level="guideline",
                pico_population=("older ADULTS",),
                pico_intervention=("Amlodipine",),
            ),
            bm25_raw_score=1.0,
            vector_raw_score=0.1,
        ),
    ]

    ranks = FeatureReranker(RetrievalConfig()).rank(query, candidates)

    assert [log.candidate.chunk.chunk_id for log in ranks] == ["guideline-pico", "rct-no-pico"]
    assert ranks[0].candidate.feature_scores["pico_match"] == 1.0
    assert ranks[0].candidate.feature_scores["evidence_level"] > ranks[1].candidate.feature_scores["evidence_level"]


def test_rank_reallocates_unavailable_pico_weight_instead_of_penalizing_candidate() -> None:
    query = Query(query_id="q-no-pico", text="hypertension treatment")
    first = _candidate("first", bm25_raw_score=3.0, vector_raw_score=0.8)
    second = _candidate("second", bm25_raw_score=2.0, vector_raw_score=0.7)

    ranks = FeatureReranker(RetrievalConfig()).rank(query, [first, second])

    assert ranks[0].candidate.feature_scores["pico_match"] is None
    assert ranks[1].candidate.feature_scores["pico_match"] is None
    # Available weights are semantic + lexical + evidence + source = 0.75;
    # the unavailable PICO and freshness weights are redistributed, not scored as zero.
    # source_quality: pubmed 表值 0.9（规划 §4.2 w6*source_quality，round2 P1 修复）。
    assert ranks[0].candidate.rerank_score == pytest.approx((0.30 + 0.20 + 0.15 * 0.20 + 0.10 * 0.9) / 0.75)
    assert ranks[0].candidate.rerank_score > ranks[1].candidate.rerank_score


def test_rank_keeps_semantic_unavailable_when_no_vector_channel_exists() -> None:
    query = Query(query_id="q-lexical", text="hypertension")
    ranks = FeatureReranker(RetrievalConfig()).rank(
        query,
        [_candidate("high", bm25_raw_score=9.0), _candidate("low", bm25_raw_score=1.0)],
    )

    assert [log.candidate.chunk.chunk_id for log in ranks] == ["high", "low"]
    assert all(log.candidate.feature_scores["semantic"] is None for log in ranks)
    assert all(log.candidate.rerank_score is not None for log in ranks)


def test_rank_orders_equal_scores_by_chunk_id_and_records_audit_fields() -> None:
    query = Query(query_id="q-tie", text="hypertension")
    ranks = FeatureReranker(RetrievalConfig(rerank_config_version="rerank-test-v1")).rank(
        query,
        [_candidate("b"), _candidate("a")],
    )

    assert [log.candidate.chunk.chunk_id for log in ranks] == ["a", "b"]
    assert [log.final_rank for log in ranks] == [1, 2]
    assert all(log.selected is False for log in ranks)
    assert all(log.rerank_config_version == "rerank-test-v1" for log in ranks)
    assert ranks[0].feature_scores == ranks[0].candidate.feature_scores


def test_rank_ignores_malformed_date_and_reallocates_freshness_weight() -> None:
    query = Query(query_id="q-latest", text="latest hypertension trial")
    malformed = _candidate("malformed", chunk=_chunk("malformed", published_at="2026-13-99"), bm25_raw_score=2.0)
    dated = _candidate("dated", chunk=_chunk("dated", published_at="2026-08-01"), bm25_raw_score=1.0)

    ranks = FeatureReranker(RetrievalConfig()).rank(query, [malformed, dated])

    by_id = {log.candidate.chunk.chunk_id: log for log in ranks}
    assert by_id["malformed"].candidate.feature_scores["freshness"] is None
    assert by_id["dated"].candidate.feature_scores["freshness"] is not None
    assert all(log.candidate.rerank_score is not None for log in ranks)


def test_latest_trial_query_favors_newer_rct_when_other_features_match() -> None:
    query = Query(query_id="q-newer", text="latest hypertension trial")
    candidates = [
        _candidate("older", chunk=_chunk("older", evidence_level="rct", published_at="2016-08-11")),
        _candidate("newer", chunk=_chunk("newer", evidence_level="rct", published_at="2026-08-11")),
    ]

    ranks = FeatureReranker(RetrievalConfig()).rank(query, candidates)

    assert [log.candidate.chunk.chunk_id for log in ranks] == ["newer", "older"]
    assert ranks[0].candidate.feature_scores["freshness"] > ranks[1].candidate.feature_scores["freshness"]  # type: ignore[operator]


def test_chinese_unsegmented_latest_query_favors_newer_evidence() -> None:
    query = Query(query_id="q-newer-zh", text="最新高血压试验")
    candidates = [
        _candidate("a-older", chunk=_chunk("a-older", evidence_level="rct", published_at="2016-08-11")),
        _candidate("z-newer", chunk=_chunk("z-newer", evidence_level="rct", published_at="2026-08-11")),
    ]

    ranks = FeatureReranker(RetrievalConfig()).rank(query, candidates)

    assert [log.candidate.chunk.chunk_id for log in ranks] == ["z-newer", "a-older"]


def test_latest_trial_evidence_mapping_favors_rct_over_guideline() -> None:
    query = Query(query_id="q-trial", text="latest hypertension trial")
    candidates = [
        _candidate("guideline", chunk=_chunk("guideline", evidence_level="guideline")),
        _candidate("rct", chunk=_chunk("rct", evidence_level="rct")),
    ]

    ranks = FeatureReranker(RetrievalConfig()).rank(query, candidates)

    assert [log.candidate.chunk.chunk_id for log in ranks] == ["rct", "guideline"]
    assert ranks[0].candidate.feature_scores["evidence_level"] == 1.0


def test_stable_topic_does_not_apply_freshness() -> None:
    query = Query(query_id="q-stable", text="hypertension evidence")
    ranks = FeatureReranker(RetrievalConfig()).rank(
        query,
        [_candidate("dated", chunk=_chunk("dated", published_at="2026-08-11"))],
    )

    assert ranks[0].candidate.feature_scores["freshness"] is None


def test_source_reliability_measures_provenance_completeness_not_evidence_level() -> None:
    query = Query(query_id="q-source", text="hypertension evidence")
    ranks = FeatureReranker(RetrievalConfig()).rank(
        query,
        [
            _candidate("guideline", chunk=_chunk("guideline", evidence_level="guideline")),
            _candidate("observational", chunk=_chunk("observational", evidence_level="observational")),
        ],
    )

    by_id = {log.candidate.chunk.chunk_id: log for log in ranks}
    assert by_id["guideline"].candidate.feature_scores["source_reliability"] == 1.0
    assert by_id["guideline"].candidate.feature_scores["source_reliability"] == by_id["observational"].candidate.feature_scores["source_reliability"]


def test_question_type_contract_field_wins_over_text_derivation() -> None:
    """round2 P1：契约字段优先于原文推导。

    评测方直接构造 question_type="latest_trial" 而文本无关键词时，题型分类与
    时效特征必须以 Query.question_type 为准：证据映射走 latest_trial（RCT 优先
    于指南），freshness 特征生效且权重提升。
    """
    query = Query(query_id="q-contract", text="hypertension evidence", question_type="latest_trial")
    ranks = FeatureReranker(RetrievalConfig()).rank(
        query,
        [
            _candidate("a-rct", chunk=_chunk("a-rct", evidence_level="rct", published_at="2026-08-01"), bm25_raw_score=2.0, vector_raw_score=0.8),
            _candidate("z-guideline", chunk=_chunk("z-guideline", evidence_level="guideline", published_at="2026-08-01"), bm25_raw_score=2.0, vector_raw_score=0.8),
        ],
    )

    by_id = {log.candidate.chunk.chunk_id: log for log in ranks}
    assert [log.candidate.chunk.chunk_id for log in ranks] == ["a-rct", "z-guideline"]
    assert by_id["a-rct"].candidate.feature_scores["evidence_level"] == 1.0
    assert by_id["a-rct"].candidate.feature_scores["freshness"] is not None
    assert by_id["a-rct"].candidate.feature_scores["freshness"] > 0.0


def test_question_type_contract_drives_freshness_feature_for_latest_trial() -> None:
    """round2 P1：契约 latest_trial 即使文本无 latest 关键词也启用 freshness。"""
    query = Query(query_id="q-contract-fresh", text="amlodipine blood pressure", question_type="latest_trial")
    ranks = FeatureReranker(RetrievalConfig()).rank(
        query,
        [
            _candidate("dated", chunk=_chunk("dated", published_at="2026-08-01"), bm25_raw_score=2.0),
            _candidate("undated", chunk=_chunk("undated"), bm25_raw_score=1.0),
        ],
    )

    by_id = {log.candidate.chunk.chunk_id: log for log in ranks}
    assert by_id["dated"].candidate.feature_scores["freshness"] is not None
    assert by_id["undated"].candidate.feature_scores["freshness"] is None
    assert [log.candidate.chunk.chunk_id for log in ranks] == ["dated", "undated"]


def test_question_type_contract_wins_for_guideline_without_keywords() -> None:
    """round2 P1：契约 guideline 不再被原文推导覆盖。"""
    query = Query(query_id="q-contract-guide", text="hypertension management", question_type="guideline")
    ranks = FeatureReranker(RetrievalConfig()).rank(
        query,
        [
            _candidate("a-rct", chunk=_chunk("a-rct", evidence_level="rct"), bm25_raw_score=2.0, vector_raw_score=0.8),
            _candidate("z-guideline", chunk=_chunk("z-guideline", evidence_level="guideline"), bm25_raw_score=2.0, vector_raw_score=0.8),
        ],
    )

    assert [log.candidate.chunk.chunk_id for log in ranks] == ["z-guideline", "a-rct"]


@pytest.mark.parametrize("query_text", ["latest hypertension guideline", "最新高血压指南"])
def test_explicit_guideline_intent_does_not_use_latest_trial_mapping(query_text: str) -> None:
    query = Query(query_id="q-guideline", text=query_text)
    ranks = FeatureReranker(RetrievalConfig()).rank(
        query,
        [
            _candidate("a-rct", chunk=_chunk("a-rct", evidence_level="rct")),
            _candidate("z-guideline", chunk=_chunk("z-guideline", evidence_level="guideline")),
        ],
    )

    assert [log.candidate.chunk.chunk_id for log in ranks] == ["z-guideline", "a-rct"]


def test_freshness_uses_explicit_query_as_of_date_not_host_clock() -> None:
    candidates = [_candidate("dated", chunk=_chunk("dated", evidence_level="rct", published_at="2020-01-01"))]
    old_query = Query(query_id="q-as-of-old", text="latest hypertension trial", as_of_date=date(2020, 1, 1))
    new_query = Query(query_id="q-as-of-new", text="latest hypertension trial", as_of_date=date(2025, 1, 1))
    reranker = FeatureReranker(RetrievalConfig())

    old_rank = reranker.rank(old_query, candidates)[0]
    new_rank = reranker.rank(new_query, candidates)[0]
    old_score = old_rank.candidate.feature_scores["freshness"]
    new_score = new_rank.candidate.feature_scores["freshness"]

    assert old_score == 1.0
    assert new_score == pytest.approx(1.0 - 1827 / 3652.5)
    assert old_rank.as_of_date == date(2020, 1, 1)
    assert new_rank.as_of_date == date(2025, 1, 1)


def test_reranker_snapshots_config_before_external_mutation() -> None:
    config = RetrievalConfig()
    reranker = FeatureReranker(config)
    query = Query(query_id="q-config-snapshot", text="hypertension treatment")
    candidates = [
        _candidate("high", bm25_raw_score=2.0, vector_raw_score=0.9),
        _candidate("low", bm25_raw_score=1.0, vector_raw_score=0.1),
    ]

    before = reranker.rank(query, candidates)
    object.__setattr__(config.feature_weights, "semantic", 10**10000)
    after = reranker.rank(query, candidates)

    assert [row.candidate.rerank_score for row in after] == [row.candidate.rerank_score for row in before]


@pytest.mark.parametrize(
    "invalid_kind",
    [
        "duplicate",
        "invalid_chunk",
    ],
)
def test_rank_rejects_duplicate_or_invalid_candidates(invalid_kind: str) -> None:
    candidates = [_candidate("duplicate"), _candidate("duplicate")]
    if invalid_kind == "invalid_chunk":
        candidates = [_candidate("invalid")]
        object.__setattr__(candidates[0], "chunk", "not-a-chunk")

    with pytest.raises(ValueError):
        FeatureReranker(RetrievalConfig()).rank(Query(query_id="q-invalid", text="hypertension"), candidates)


def test_rank_rejects_candidate_with_mutated_invalid_chunk_pico_data() -> None:
    candidate = _candidate("invalid-pico")
    object.__setattr__(candidate.chunk, "pico_population", ("",))

    with pytest.raises(ValueError, match="pico_population"):
        FeatureReranker(RetrievalConfig()).rank(Query(query_id="q-invalid-pico", text="hypertension"), [candidate])


def test_rank_rejects_a_query_with_mutated_non_string_language() -> None:
    query = Query(query_id="q-invalid-language", text="hypertension")
    object.__setattr__(query, "language", 12)

    with pytest.raises(ValueError, match="language"):
        FeatureReranker(RetrievalConfig()).rank(query, [_candidate("valid")])
