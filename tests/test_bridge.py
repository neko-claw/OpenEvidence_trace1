"""Tests for the A5/A6 integration bridge (a5.ports.EvidenceRetriever 适配)."""

from __future__ import annotations

from a5.retrieval_bridge import A5EvidenceRetriever
from retrieval.bm25 import BM25Index
from retrieval.config import RetrievalConfig
from retrieval.models import EvidenceChunk, SearchStatus
from retrieval.ports import Question, RetrievalRequest, RetrievalResult, SearchPlan, question_to_query
from retrieval.service import RetrievalService
from retrieval.vector import InMemoryVectorSearch


def _chunk(chunk_id: str, **changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": chunk_id,
        "evidence_id": f"evidence-{chunk_id}",
        "stable_id": f"PMID:{chunk_id}",
        "text": f"Clinical evidence about {chunk_id} for hypertension treatment.",
        "title": f"Study of {chunk_id}",
        "source_type": "pubmed",
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{chunk_id}/",
        "evidence_level": "rct",
        "topic": "hypertension",
        "content_vector": (1.0, 0.0),
        "index_version": "idx-bridge",
        "corpus_version": "corpus-bridge",
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


def _service(chunks: tuple[EvidenceChunk, ...]) -> RetrievalService:
    return RetrievalService(
        BM25Index(chunks),
        InMemoryVectorSearch({chunk.chunk_id: (chunk, chunk.content_vector) for chunk in chunks}),
        lambda query: (1.0, 0.0),
        RetrievalConfig(
            bm25_top_k=5,
            vector_top_k=5,
            fusion_top_k=5,
            rerank_top_k=5,
            selection_top_k=2,
            index_version="idx-bridge",
            corpus_version="corpus-bridge",
            rerank_config_version="rerank-bridge",
        ),
    )


def test_bridge_returns_port_payload_with_selected_chunks() -> None:
    chunks = (
        _chunk("amlodipine", text="Amlodipine reduced blood pressure in older adults with hypertension."),
        _chunk("losartan"),
    )
    adapter = A5EvidenceRetriever(_service(chunks))
    request = RetrievalRequest(
        question=Question(
            question_id="q-bridge",
            text="老年高血压患者的氨氯地平治疗证据",
            english_terms=("amlodipine", "hypertension", "older adults"),
        ),
        plan=SearchPlan(topic="therapy", domain="hypertension"),
    )

    result = adapter.retrieve(request)

    assert isinstance(result, RetrievalResult)
    assert result.question_id == "q-bridge"
    assert result.status in {"ok", "partial"}
    assert result.selected_chunks
    assert all(isinstance(chunk, EvidenceChunk) for chunk in result.selected_chunks)
    assert result.rank_log
    assert result.index_version == "idx-bridge"
    assert result.rerank_config_version == "rerank-bridge"
    assert result.out_of_scope is False


def test_bridge_plan_overrides_are_applied() -> None:
    chunks = (_chunk("amlodipine"),)
    adapter = A5EvidenceRetriever(_service(chunks))
    request = RetrievalRequest(
        question=Question(question_id="q-plan", text="hypertension evidence"),
        plan=SearchPlan(source_types=("guideline",), evidence_levels=("rct",)),
    )

    result = adapter.retrieve(request)

    # source_types=guideline 过滤掉 pubmed 来源 → 空结果，而不是越界返回。 
    assert result.status == "empty"


def test_bridge_out_of_scope_returns_empty_with_explicit_reason() -> None:
    chunks = (_chunk("amlodipine"),)
    adapter = A5EvidenceRetriever(_service(chunks))
    request = RetrievalRequest(
        question=Question(
            question_id="q-dose",
            text="帮我算一下我应该吃多少毫克氨氯地平",
            out_of_scope=True,
        )
    )

    result = adapter.retrieve(request)

    assert result.status == "empty"
    assert "out_of_scope" in result.degradation_reasons
    assert result.selected_chunks == ()
    assert result.out_of_scope is True


def test_question_to_query_maps_all_port_fields() -> None:
    query = question_to_query(
        Question(
            question_id="q1",
            text="text",
            pico_population=("older adults",),
            atomic_claims=("claim",),
            out_of_scope=True,
        ),
        SearchPlan(topic="therapy", question_type="guideline", freshness="current", domain="hypertension"),
    )

    assert query.query_id == "q1"
    assert query.topic == "therapy"
    assert query.question_type == "guideline"
    assert query.freshness == "current"
    assert query.domain == "hypertension"
    assert query.pico_population == ("older adults",)
    assert query.atomic_claims == ("claim",)
    assert query.out_of_scope is True


def test_bridge_search_query_returns_native_search_result() -> None:
    chunks = (_chunk("amlodipine"),)
    adapter = A5EvidenceRetriever(_service(chunks))
    query = question_to_query(
        Question(question_id="q-native", text="amlodipine hypertension"),
        SearchPlan(domain="hypertension"),
    )

    result = adapter.search_query(query)

    assert result.query_id == "q-native"
    assert result.status in {SearchStatus.OK, SearchStatus.PARTIAL}
