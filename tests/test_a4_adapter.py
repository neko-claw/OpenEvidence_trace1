"""A5 adapter contract tests: A4EvidenceRetrieverAdapter satisfies the REAL
``a5.ports.EvidenceRetriever`` protocol and maps A4 output faithfully.

These tests use A5's actual Pydantic types from ``a5.domain.models`` — nothing
is redefined or shadowed.
"""

from __future__ import annotations

import pytest

from a5.adapters.a4_evidence_retriever import A4EvidenceRetrieverAdapter
from a5.domain.models import Question, RetrievalRequest, RetrievalResult, SearchPlan
from a5.ports.evidence_retriever import EvidenceRetriever

from retrieval.config import RetrievalConfig
from retrieval.models import EvidenceChunk, Query, SearchResult, SearchStatus


def _chunk(chunk_id: str, **changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": chunk_id,
        "evidence_id": f"evidence-{chunk_id}",
        "stable_id": f"upstream:MOCK-A4-{chunk_id}",
        "text": f"Clinical evidence about {chunk_id} for hypertension treatment.",
        "title": f"Study of {chunk_id}",
        "source_type": "pubmed",
        "url": "",
        "evidence_level": "rct",
        "topic": "hypertension",
        "published_at": "2024-01-15",
        "evidence_content_hash": "upstream-evidence-hash",
        "content_hash": "upstream-chunk-hash",
        "mock": True,
        "index_version": "idx-bridge",
        "corpus_version": "corpus-bridge",
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


class FakeService:
    """Injectable fake for deterministic adapter tests."""

    def __init__(self, result: SearchResult | None = None) -> None:
        self._result = result
        self.calls: list[Query] = []

    def search(self, query: Query) -> SearchResult:
        self.calls.append(query)
        if self._result is None:
            return SearchResult(
                query_id=query.query_id,
                index_version="idx-bridge",
                corpus_version="corpus-bridge",
                rerank_config_version="rerank-bridge",
                status=SearchStatus.EMPTY,
            )
        return self._result


def _config() -> RetrievalConfig:
    return RetrievalConfig(
        selection_top_k=2,
        index_version="idx-bridge",
        corpus_version="corpus-bridge",
        rerank_config_version="rerank-bridge",
    )


def _plan() -> SearchPlan:
    return SearchPlan(
        queries=["amlodipine hypertension"],
        preferred_sources=["pubmed"],
        freshness_required=False,
        expected_evidence_types=["rct"],
        max_tool_calls=3,
    )


def _question(**changes: object) -> Question:
    values: dict[str, object] = {
        "question_id": "Q-ADAPTER-001",
        "text": "老年高血压患者的氨氯地平治疗证据",
        "metadata": {"domain": "hypertension"},
    }
    values.update(changes)
    return Question(**values)  # type: ignore[arg-type]


def _ok_result(
    chunks: tuple[EvidenceChunk, ...], *, calibrated_quality: float | None = None
) -> SearchResult:
    from retrieval.models import RankLog, ScoredChunk, Candidate

    candidates = [
        Candidate(
            chunk=chunk,
            bm25_rank=rank,
            bm25_raw_score=1.0,
            rrf_score=0.05,
            rerank_score=0.95 - rank * 0.05,
            feature_scores={"semantic": 0.9},
        )
        for rank, chunk in enumerate(chunks, start=1)
    ]
    return SearchResult(
        query_id="Q-ADAPTER-001",
        index_version="idx-bridge",
        corpus_version="corpus-bridge",
        rerank_config_version="rerank-bridge",
        status=SearchStatus.OK,
        selected_chunks=chunks,
        rank_log=tuple(
            RankLog(
                candidate=candidate,
                feature_scores=candidate.feature_scores,
                final_rank=rank,
                selected=rank <= len(chunks),
                rerank_config_version="rerank-bridge",
            )
            for rank, candidate in enumerate(candidates, start=1)
        ),
        degradation_reasons=(),
        degradation_codes=(),
        retrieval_warning=None,
        latency_ms=12,
        stage_latency_ms={"total": 12},
        run_hash="run-hash-abc",
        reason_code_version="reason-codes-v1",
        quality_scores=(
            {chunk.chunk_id: calibrated_quality for chunk in chunks}
            if calibrated_quality is not None
            else {}
        ),
        quality_score_kind="QUALITY" if calibrated_quality is not None else "UNKNOWN",
        quality_score_scope="CROSS_QUERY" if calibrated_quality is not None else "UNKNOWN",
        quality_score_calibrated=calibrated_quality is not None,
    )


def test_adapter_satisfies_real_evidence_retriever_protocol() -> None:
    adapter = A4EvidenceRetrieverAdapter(FakeService(), _config())

    assert isinstance(adapter, EvidenceRetriever)


def test_retrieve_uses_three_parameter_signature_and_returns_a5_result() -> None:
    service = FakeService()
    adapter = A4EvidenceRetrieverAdapter(service, _config())

    result = adapter.retrieve(_question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1))

    assert isinstance(result, RetrievalResult)
    assert result.tool_name == "a4_evidence_retrieval"
    assert service.calls
    assert service.calls[0].source_types == ("pubmed",)


def test_request_source_type_limits_this_tool_call() -> None:
    service = FakeService()
    adapter = A4EvidenceRetrieverAdapter(service, _config())

    adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="guideline", tool_call_index=1)
    )

    assert service.calls[0].source_types == ("guideline",)


def test_tool_call_index_enters_diagnostics() -> None:
    adapter = A4EvidenceRetrieverAdapter(FakeService(), _config())

    result = adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=2)
    )

    assert result.diagnostics["tool_call_index"] == 2
    assert result.diagnostics["requested_source"] == "pubmed"


def test_partial_empty_failed_are_never_upgraded() -> None:
    for status, evidence in (
        (SearchStatus.PARTIAL, ("e1",)),
        (SearchStatus.EMPTY, ()),
        (SearchStatus.FAILED, ()),
    ):
        chunks = (_chunk("e1"),)
        result = SearchResult(
            query_id="Q",
            index_version="idx-bridge",
            corpus_version="corpus-bridge",
            rerank_config_version="rerank-bridge",
            status=status,
            selected_chunks=chunks if evidence else (),
            degradation_reasons=["vector_unavailable"],
            degradation_codes=["vector_unavailable"],
        )
        adapter = A4EvidenceRetrieverAdapter(FakeService(result), _config())
        payload = adapter.retrieve(
            _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1)
        )

        assert payload.diagnostics["status"] == status.value
        if evidence:
            assert [record.id for record in payload.evidence]
        else:
            assert payload.evidence == []
        assert payload.diagnostics["degraded"] is True


def test_selected_chunks_map_to_evidence_records() -> None:
    chunk = _chunk(
        "c1",
        pico_population=("older adults",),
        pico_intervention=("amlodipine",),
        pico_outcome=("blood pressure",),
    )
    adapter = A4EvidenceRetrieverAdapter(FakeService(_ok_result((chunk,))), _config())

    payload = adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1)
    )

    record = payload.evidence[0]
    assert record.id == "evidence-c1::c1"  # 冻结的 citation_id_rule
    assert record.content == chunk.text
    assert record.source_type == "pubmed"
    assert record.retrieval_score is None
    assert record.source_metadata["ranking_score"] == pytest.approx(0.9)
    assert record.published_at is not None
    assert record.population == "older adults"
    assert record.intervention == "amlodipine"
    assert record.outcome == "blood pressure"
    assert record.mock is True
    assert record.source_metadata["evidence_content_hash"] == "upstream-evidence-hash"
    assert record.source_metadata["chunk_content_hash"] == "upstream-chunk-hash"
    assert record.source_metadata["provenance_unknown"] is False


def test_only_explicit_calibrated_quality_enters_gate2_score_contract() -> None:
    chunk = _chunk("quality")
    adapter = A4EvidenceRetrieverAdapter(
        FakeService(_ok_result((chunk,), calibrated_quality=0.82)), _config()
    )

    payload = adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1)
    )

    record = payload.evidence[0]
    assert record.retrieval_score == pytest.approx(0.82)
    assert record.retrieval_score_kind.value == "QUALITY"
    assert record.retrieval_score_scope.value == "CROSS_QUERY"
    assert record.retrieval_score_calibrated is True


def test_spans_stay_empty_and_never_synthesized() -> None:
    adapter = A4EvidenceRetrieverAdapter(FakeService(_ok_result((_chunk("c1"),))), _config())

    payload = adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1)
    )

    assert payload.evidence[0].spans == []
    assert payload.diagnostics["span_status"] == "UNKNOWN_A3_PENDING"


def test_diagnostics_carry_status_versions_warning_and_config_snapshot() -> None:
    adapter = A4EvidenceRetrieverAdapter(FakeService(_ok_result((_chunk("c1"),))), _config())

    payload = adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1)
    )

    diag = payload.diagnostics
    assert diag["status"] == "ok"
    assert diag["versions"]["index_version"] == "idx-bridge"
    assert diag["versions"]["rerank_config_version"] == "rerank-bridge"
    assert diag["run_hash"] == "run-hash-abc"
    assert diag["config_snapshot"]["citation_id_rule"] == "evidence_id::chunk_id"
    assert diag["config_hash"]
    assert diag["latency_ms"] == 12
    assert "retrieval_warning" in diag


def test_alignment_hints_never_become_verification_supported() -> None:
    """token overlap 永不产生 A5 SUPPORTED：hints 只进 diagnostics。"""
    from retrieval.models import RetrievalAlignmentHint

    chunk = _chunk("c1", text="amlodipine reduces blood pressure in older adults with hypertension")
    result = _ok_result((chunk,))
    result = SearchResult(
        query_id=result.query_id,
        index_version=result.index_version,
        corpus_version=result.corpus_version,
        rerank_config_version=result.rerank_config_version,
        status=result.status,
        selected_chunks=result.selected_chunks,
        rank_log=result.rank_log,
        alignment_hints=(
            RetrievalAlignmentHint(
                claim_index=0,
                claim_text="amlodipine reduces blood pressure in older adults",
                decision="ALIGNED",
                evidence_ids=("evidence-c1",),
                method="token_overlap_heuristic",
                threshold_version="p0-v1",
            ),
        ),
    )
    adapter = A4EvidenceRetrieverAdapter(FakeService(result), _config())

    payload = adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1)
    )

    hints = payload.diagnostics["alignment_hints"]
    assert hints[0]["decision"] == "ALIGNED"
    assert hints[0]["method"] == "token_overlap_heuristic"
    # A5 VerificationStatus.SUPPORTED 出现在 A5 的验证结果中，但 A4 hint 永远不是它。
    from a5.domain.enums import VerificationStatus

    assert hints[0]["decision"] != VerificationStatus.SUPPORTED.value
    # Gate5 用 A5 的 verifier：高 token overlap 的 hint 不进入任何 A5 SUPPORTED 判定。
    from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
    from a5.domain.models import Claim, VerificationContext
    from a5.domain.enums import ClaimCriticality

    claim = Claim(
        claim_id="C1",
        text="amlodipine reduces blood pressure in older adults",
        criticality=ClaimCriticality.IMPORTANT,
        evidence_ids=["evidence-c1::c1"],
        evidence_span_ids=["S-NONE"],  # A4 未提供 span → Gate5 span_check 不是 MATCH
    )
    verdict = RuleBasedClaimVerifier().verify(
        claim,
        payload.evidence,
        VerificationContext(freshness_required=False),
    )
    assert verdict.status != VerificationStatus.SUPPORTED


def test_upstream_content_hash_is_preserved_not_overwritten() -> None:
    chunk = _chunk("c1", content_hash="upstream-chunk-hash", evidence_content_hash="upstream-evidence-hash")

    assert chunk.content_hash == "upstream-chunk-hash"
    assert chunk.provenance_complete is True
    # A4 无法用自家算法验证 A3 hash 与内容的一致性：诚实标记，不伪造一致性。
    assert chunk.content_hash_mismatch is True


def test_a4_fallback_hash_is_used_only_when_upstream_absent() -> None:
    chunk = _chunk("c1", content_hash="", evidence_content_hash="")

    assert chunk.content_hash  # A4 fallback（仅上游缺失时）
    assert chunk.provenance_complete is False
    assert chunk.content_hash_mismatch is False


def test_missing_provenance_is_reported_unknown_not_fabricated() -> None:
    chunk = _chunk("c1", content_hash="", evidence_content_hash="")
    adapter = A4EvidenceRetrieverAdapter(FakeService(_ok_result((chunk,))), _config())

    payload = adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1)
    )

    record = payload.evidence[0]
    assert record.source_metadata["provenance_unknown"] is True
    assert payload.diagnostics["provenance_unknown_chunks"] == ["c1"]
    # A4 的 fallback hash 不冒充上游身份
    assert record.source_metadata["chunk_content_hash"] != ""


def test_mock_chunks_are_marked_mock_in_evidence_records() -> None:
    chunk = _chunk("c1", mock=True, stable_id="MOCK-A4-E001")
    adapter = A4EvidenceRetrieverAdapter(FakeService(_ok_result((chunk,))), _config())

    payload = adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1)
    )

    assert payload.evidence[0].mock is True


def test_out_of_scope_question_returns_defensive_empty_with_reason() -> None:
    empty = SearchResult(
        query_id="Q",
        index_version="idx-bridge",
        corpus_version="corpus-bridge",
        rerank_config_version="rerank-bridge",
        status=SearchStatus.EMPTY,
        degradation_reasons=["out_of_scope"],
        degradation_codes=["out_of_scope"],
    )
    adapter = A4EvidenceRetrieverAdapter(FakeService(empty), _config())

    payload = adapter.retrieve(
        _question(metadata={"out_of_scope": True, "domain": "hypertension"}),
        _plan(),
        RetrievalRequest(source_type="pubmed", tool_call_index=1),
    )

    assert payload.evidence == []
    assert payload.diagnostics["status"] == "empty"
    assert "out_of_scope" in payload.diagnostics["degradation_codes"]
    assert payload.diagnostics["out_of_scope"] is True


def test_a3_span_provider_maps_real_spans_and_flags_available() -> None:
    """评审项 4：A3 Span Schema 已落地（contracts/a3/v0.2），真实 span 通过
    provider 接入；A4 不定义 schema、不合成 span ID。"""
    from a3.domain.models import EvidenceSpan as A3EvidenceSpan

    chunk = _chunk("c1")
    a3_span = A3EvidenceSpan(
        span_id="S-A3-001",
        evidence_id=chunk.evidence_id,
        chunk_id=chunk.chunk_id,
        text="Exact synthetic claim about the artificial outcome.",
        char_start=0,
        char_end=51,
        document_char_start=10,
        document_char_end=61,
        chunk_content_hash="chunk-hash",
        evidence_content_hash="evidence-hash",
        content_hash="span-hash",
        page=7,
        section="mock results",
    )
    adapter = A4EvidenceRetrieverAdapter(
        FakeService(_ok_result((chunk,))),
        _config(),
        span_provider=lambda chunk_id: [a3_span] if chunk_id == "c1" else [],
    )

    payload = adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1)
    )

    record = payload.evidence[0]
    assert len(record.spans) == 1
    assert record.spans[0].span_id == "S-A3-001"
    assert record.spans[0].text == a3_span.text
    assert record.spans[0].chunk_id == "c1"
    assert record.spans[0].page == 7
    assert record.spans[0].section == "mock results"
    assert payload.diagnostics["span_status"] == "A3_AVAILABLE"


def test_a3_span_provider_missing_span_stays_absent() -> None:
    """provider 未返回该 chunk 的 span 时保持缺席（UNKNOWN），不猜测。"""
    chunk = _chunk("c1")
    adapter = A4EvidenceRetrieverAdapter(
        FakeService(_ok_result((chunk,))),
        _config(),
        span_provider=lambda chunk_id: [],  # 该 chunk 无 span
    )

    payload = adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1)
    )

    assert payload.evidence[0].spans == []
    assert payload.diagnostics["span_status"] == "A3_AVAILABLE"


def test_span_provider_never_invents_span_ids_for_missing_fields() -> None:
    class BrokenSpan:
        """缺 span_id 的对象：adapter 必须跳过而非合成。"""

        text = "some text"

    adapter = A4EvidenceRetrieverAdapter(
        FakeService(_ok_result((_chunk("c1"),))),
        _config(),
        span_provider=lambda chunk_id: [BrokenSpan()],
    )

    payload = adapter.retrieve(
        _question(), _plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1)
    )

    assert payload.evidence[0].spans == []
