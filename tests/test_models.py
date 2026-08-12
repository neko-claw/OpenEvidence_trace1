import pytest
from datetime import datetime

from retrieval.config import FeatureWeights, RetrievalConfig
from retrieval.models import DEFAULT_AS_OF_DATE, Candidate, EvidenceChunk, Query, RankLog, ScoredChunk, SearchResult, SearchStatus


def evidence_chunk(**changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": "chunk-001",
        "evidence_id": "evidence-001",
        "stable_id": "PMID:123456",
        "text": "A randomized clinical trial found a clinically meaningful outcome.",
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["chunk_id", "evidence_id", "stable_id", "text"])
def test_evidence_chunk_rejects_blank_required_fields(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        evidence_chunk(**{field: "   "})


def test_evidence_chunk_has_safe_a4_metadata_defaults() -> None:
    chunk = evidence_chunk()

    assert chunk.title == ""
    assert chunk.source_type == ""
    assert chunk.url == ""
    assert chunk.published_at is None
    assert chunk.evidence_level == "unknown"
    assert chunk.population_terms == ()
    assert chunk.intervention_terms == ()
    assert chunk.comparator_terms == ()
    assert chunk.outcome_terms == ()
    assert chunk.embedding == ()
    assert chunk.is_tombstoned is False
    assert chunk.index_version == "v1"
    assert chunk.corpus_version == "v1"
    with pytest.raises(Exception):
        chunk.text = "mutated"  # type: ignore[misc]


def test_default_config_is_valid_and_uses_p0_defaults() -> None:
    config = RetrievalConfig()

    assert (
        config.bm25_top_k,
        config.vector_top_k,
        config.fusion_top_k,
        config.rerank_top_k,
        config.selection_top_k,
    ) == (50, 50, 80, 25, 8)  # selection_top_k 与冻结 YAML 一致（round2 P2 修复）
    assert config.rrf_k == 60
    assert config.max_chunks_per_document == 2
    assert config.max_chunks_per_source == 4
    assert config.mmr_lambda == 0.75
    assert config.feature_weights == FeatureWeights(
        semantic=0.30,
        lexical=0.20,
        pico_match=0.15,
        evidence_level=0.15,
        freshness=0.10,
        source_reliability=0.10,
    )
    assert config.index_version
    assert config.rerank_config_version


def test_config_rejects_feature_weights_that_do_not_sum_to_one() -> None:
    weights = FeatureWeights()
    object.__setattr__(weights, "semantic", 0.5)

    with pytest.raises(ValueError, match="sum to one"):
        RetrievalConfig(feature_weights=weights)


def test_config_rejects_a_non_float_representable_rrf_k() -> None:
    with pytest.raises(ValueError, match="rrf_k"):
        RetrievalConfig(rrf_k=10**10000)


def test_feature_reranker_rejects_a_mutated_non_float_representable_weight() -> None:
    from retrieval.rerank import FeatureReranker

    weights = FeatureWeights()
    object.__setattr__(weights, "semantic", 10**10000)

    with pytest.raises(ValueError, match="feature weights"):
        FeatureReranker(RetrievalConfig(feature_weights=weights))


def test_config_rejects_a_non_float_representable_mmr_lambda() -> None:
    with pytest.raises(ValueError, match="mmr_lambda"):
        RetrievalConfig(mmr_lambda=10**10000)


@pytest.mark.parametrize("status", [SearchStatus.OK, SearchStatus.PARTIAL, SearchStatus.EMPTY, SearchStatus.FAILED])
def test_search_result_accepts_all_declared_statuses(status: SearchStatus) -> None:
    result = SearchResult(
        query_id="query-1",
        index_version="index-20260811",
        rerank_config_version="rerank-20260811",
        status=status,
        selected_chunks=(),
        rank_log=(RankLog(),),
    )

    assert result.status is status


@pytest.mark.parametrize(
    ("query_id", "index_version", "rerank_config_version"),
    [("", "index-v1", "rerank-v1"), ("query-1", " ", "rerank-v1"), ("query-1", "index-v1", "")],
)
def test_search_result_rejects_blank_identity_or_version_fields(
    query_id: str, index_version: str, rerank_config_version: str
) -> None:
    with pytest.raises(ValueError):
        SearchResult(
            query_id=query_id,
            index_version=index_version,
            rerank_config_version=rerank_config_version,
            status=SearchStatus.OK,
            selected_chunks=(),
            rank_log=(RankLog(),),
        )


def test_search_result_rejects_a_blank_corpus_version() -> None:
    with pytest.raises(ValueError, match="corpus_version"):
        SearchResult(
            query_id="query-1",
            index_version="index-v1",
            corpus_version=" ",
            rerank_config_version="rerank-v1",
            status=SearchStatus.OK,
        )


def test_query_requires_a_nonblank_id_and_text() -> None:
    with pytest.raises(ValueError, match="query_id"):
        Query(query_id=" ", text="hypertension treatment")
    with pytest.raises(ValueError, match="text"):
        Query(query_id="query-1", text=" ")


def test_query_normalizes_pico_iterables_to_immutable_tuples() -> None:
    population = ["older adults"]
    query = Query(query_id="query-1", text="hypertension treatment", pico_population=population)

    population.append("patients with diabetes")

    assert query.pico_population == ("older adults",)
    assert isinstance(query.pico_population, tuple)


def test_query_accepts_structured_retrieval_fields_and_immutable_explicit_english_terms() -> None:
    english_terms = ["hypertension", "amlodipine"]
    query = Query(
        query_id="query-structured",
        text="老年高血压的氨氯地平治疗",
        topic="therapy",
        question_type="therapy",
        freshness="current",
        english_terms=english_terms,
    )

    english_terms.append("mutated")

    assert query.topic == "therapy"
    assert query.question_type == "therapy"
    assert query.freshness == "current"
    assert query.english_terms == ("hypertension", "amlodipine")


@pytest.mark.parametrize("field", ["topic", "question_type", "freshness"])
def test_query_rejects_unknown_structured_retrieval_categories(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        Query(query_id="query-invalid-category", text="hypertension", **{field: "unsupported"})


def test_query_uses_a_deterministic_frozen_default_as_of_date() -> None:
    assert Query(query_id="query-as-of", text="hypertension").as_of_date == DEFAULT_AS_OF_DATE


def test_query_rejects_an_invalid_explicit_as_of_date() -> None:
    with pytest.raises(ValueError, match="as_of_date"):
        Query(query_id="query-invalid-as-of", text="hypertension", as_of_date=None)  # type: ignore[arg-type]


def test_query_rejects_datetime_as_as_of_date() -> None:
    with pytest.raises(ValueError, match="as_of_date"):
        Query(query_id="query-datetime-as-of", text="hypertension", as_of_date=datetime(2026, 8, 11))  # type: ignore[arg-type]


def test_score_feature_maps_are_copied_and_immutable() -> None:
    scores = {"semantic": 0.8}
    scored_chunk = ScoredChunk(chunk=evidence_chunk(), score=0.8, rank=1, stage="vector", feature_scores=scores)
    candidate = Candidate(chunk=evidence_chunk(), feature_scores=scores)

    scores["semantic"] = 0.1

    assert scored_chunk.feature_scores["semantic"] == 0.8
    assert candidate.feature_scores["semantic"] == 0.8
    with pytest.raises(TypeError):
        scored_chunk.feature_scores["semantic"] = 0.1  # type: ignore[index]


@pytest.mark.parametrize(
    ("factory", "feature_scores"),
    [
        (lambda values: ScoredChunk(evidence_chunk(), 0.8, 1, "vector", values), {" ": 0.8}),
        (lambda values: Candidate(evidence_chunk(), feature_scores=values), {"semantic": float("inf")}),
    ],
)
def test_score_feature_maps_reject_invalid_keys_or_values(factory: object, feature_scores: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        factory(feature_scores)  # type: ignore[operator]


def test_search_result_normalizes_nested_collections_and_rejects_wrong_types() -> None:
    chunk = evidence_chunk()
    rank_log = RankLog(candidate=Candidate(chunk=chunk))
    result = SearchResult(
        query_id="query-1",
        index_version="index-v1",
        rerank_config_version="rerank-v1",
        status=SearchStatus.OK,
        selected_chunks=[chunk],
        rank_log=[rank_log],
    )

    assert result.selected_chunks == (chunk,)
    assert result.rank_log == (rank_log,)
    with pytest.raises(ValueError, match="selected_chunks"):
        SearchResult(
            query_id="query-1",
            index_version="index-v1",
            rerank_config_version="rerank-v1",
            status=SearchStatus.OK,
            selected_chunks=("not a chunk",),  # type: ignore[arg-type]
            rank_log=(),
        )


def test_rank_log_rejects_a_non_candidate_primary_candidate() -> None:
    with pytest.raises(ValueError, match="candidate"):
        RankLog(candidate="not a candidate")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("factory", "field_name"),
    [
        (lambda: ScoredChunk(evidence_chunk(), 10**10000, 1, "bm25"), "score"),
        (lambda: Candidate(evidence_chunk(), bm25_raw_score=10**10000), "bm25_raw_score"),
        (lambda: ScoredChunk(evidence_chunk(), 1.0, 10**10000, "bm25"), "rank"),
        (lambda: Candidate(evidence_chunk(), vector_rank=10**10000), "vector_rank"),
    ],
)
def test_score_and_rank_contracts_reject_non_float_representable_integers(factory: object, field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        factory()  # type: ignore[operator]


def test_evidence_chunk_carries_gate1_provenance_fields() -> None:
    chunk = evidence_chunk(
        pmid="33000020",
        doi="10.1000/example",
        nct_id="NCT05500001",
        authors=("Wang H", "Li Y"),
        guideline_name="中国高血压防治指南（2024年修订版）",
        fetched_at="2026-08-10T09:00:00Z",
    )

    assert chunk.pmid == "33000020"
    assert chunk.doi == "10.1000/example"
    assert chunk.nct_id == "NCT05500001"
    assert chunk.authors == ("Wang H", "Li Y")
    assert chunk.guideline_name == "中国高血压防治指南（2024年修订版）"
    assert chunk.fetched_at == "2026-08-10T09:00:00Z"


def test_evidence_chunk_validates_provenance_fields() -> None:
    with pytest.raises(ValueError, match="pmid"):
        evidence_chunk(pmid=123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="authors"):
        evidence_chunk(authors=("",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="fetched_at"):
        evidence_chunk(fetched_at=123)  # type: ignore[arg-type]


def test_evidence_chunk_accepts_iso_strings_for_fetched_at() -> None:
    chunk = evidence_chunk(fetched_at="2026-08-10T09:00:00Z")

    assert chunk.fetched_at == "2026-08-10T09:00:00Z"


def test_evidence_chunk_defaults_remain_backward_compatible() -> None:
    chunk = evidence_chunk()

    assert chunk.pmid == ""
    assert chunk.doi == ""
    assert chunk.nct_id == ""
    assert chunk.authors == ()
    assert chunk.guideline_name == ""
    assert chunk.fetched_at is None


def test_query_carries_out_of_scope_flag() -> None:
    from retrieval.models import Query

    query = Query(query_id="q1", text="帮我算一下服用多少毫克", out_of_scope=True)

    assert query.out_of_scope is True
    with pytest.raises(ValueError, match="out_of_scope"):
        Query(query_id="q2", text="正常问题", out_of_scope="yes")  # type: ignore[arg-type]
