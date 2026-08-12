from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from a5.adapters.mock_claim_generator import MockClaimGenerator
from a5.adapters.provisional import (
    A1QuestionAdapter,
    A1QuestionPayload,
    A1SafetyPolicyAdapter,
    A2EvidenceAdapter,
    A2EvidencePayload,
    A2MCPRetriever,
    A2ToA3EvidenceAdapter,
    A3EvidenceAdapter,
    A4RAGRetriever,
    UpstreamContractError,
    UpstreamRetrievalError,
)
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.agent.workflow import A5Workflow
from a5.domain.enums import Decision, SafetyDecision
from a5.domain.models import Question, RetrievalRequest, RetrievalResult, SearchPlan
from a5.ports.evidence_retriever import EvidenceRetriever
from a5.ports.safety_policy import SafetyPolicy
from a5.runtime_config import load_runtime_config
from a5.skills.evidence_research import EvidenceResearchSkill


def a1_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "DEV-HTN-01",
        "split": "DEV",
        "dataset_pack": "openevidence-dev-v0.1",
        "topic": "hypertension",
        "difficulty": "medium",
        "language": "zh-CN",
        "question": "成年人高血压指南证据应如何检索？",
        "question_type": "guideline_treatment",
        "answerable": True,
        "as_of_date": "2026-08-11",
        "source_provenance": {
            "origin": "a1_blueprint",
            "authoring_method": "human-authored contract fixture",
            "candidate_sources": [],
        },
        "source_group_id": "SG-DEV-HTN-01",
        "gold_source_ids": [],
        "rubric_version": "rubric-candidate-v0.1",
        "expected_source_types": ["current_guideline", "pubmed_review"],
        "critical_answer_points": ["Identify the evidence route"],
        "contraindicating_evidence": [],
        "penalty_points": ["No individualized prescribing"],
        "evidence_gap_label": "none_expected",
        "review_status": "A1_COMPLETE_B2_GOLD_PENDING",
    }
    payload.update(changes)
    return payload


def plan(source: str = "guideline") -> SearchPlan:
    return SearchPlan(
        queries=["mock contract query"],
        preferred_sources=[source],
        freshness_required=False,
        expected_evidence_types=["guideline"],
        max_tool_calls=1,
    )


def request(source: str = "guideline") -> RetrievalRequest:
    return RetrievalRequest(source_type=source, tool_call_index=1)


def test_a1_contract_is_strict_and_schema_exportable() -> None:
    validated = A1QuestionPayload.model_validate(a1_payload())
    schema = A1QuestionPayload.model_json_schema()
    assert validated.question_type == "guideline_treatment"
    assert schema["additionalProperties"] is False
    assert "question_type" in schema["properties"]
    assert set(schema["properties"]) == {
        "id",
        "split",
        "dataset_pack",
        "topic",
        "difficulty",
        "language",
        "question",
        "question_type",
        "answerable",
        "as_of_date",
        "source_provenance",
        "source_group_id",
        "gold_source_ids",
        "rubric_version",
        "expected_source_types",
        "critical_answer_points",
        "contraindicating_evidence",
        "penalty_points",
        "evidence_gap_label",
        "review_status",
    }
    with pytest.raises(ValidationError):
        A1QuestionPayload.model_validate(a1_payload(unplanned_field=True))


def test_a1_question_type_actually_drives_skill_plan() -> None:
    question = A1QuestionAdapter().adapt(a1_payload())
    skill = EvidenceResearchSkill(load_runtime_config())
    generated = skill.plan(question)
    assert generated.question_type == "guideline_treatment"
    assert generated.search_plan.preferred_sources[0] == "current_guideline"
    assert generated.search_plan.freshness_required is True
    assert generated.search_plan.max_tool_calls == 3


class StaticA1Evaluator:
    def __init__(self, decision: str = "ALLOW") -> None:
        self.decision = decision

    def assess(self, policy_input: object) -> object:
        del policy_input
        return {
            "decision": self.decision,
            "reason_codes": ["safety_scope_allowed"],
            "matched_rules": ["G0_ALLOWED_SCOPE"],
            "termination_action": "CONTINUE",
            "user_message_key": "gate0.allowed",
            "policy_version": "a1-safety-v0.2",
        }


class BrokenA1Evaluator:
    def assess(self, policy_input: object) -> object:
        del policy_input
        raise RuntimeError("A1 unavailable")


class InconsistentA1Evaluator(StaticA1Evaluator):
    def assess(self, policy_input: object) -> object:
        result = super().assess(policy_input)
        result["termination_action"] = "REFUSE"
        return result


def test_a1_safety_adapter_requires_explicit_valid_verdict() -> None:
    allowed = A1SafetyPolicyAdapter(StaticA1Evaluator()).assess(
        Question(text="test question", metadata={"a1_safety_signals": {"topic": "hypertension"}})
    )
    unknown = A1SafetyPolicyAdapter(BrokenA1Evaluator()).assess(Question(text="test question"))
    assert allowed.decision is SafetyDecision.ALLOW
    assert unknown.decision is SafetyDecision.UNKNOWN
    assert isinstance(A1SafetyPolicyAdapter(StaticA1Evaluator()), SafetyPolicy)


def test_a1_inconsistent_decision_and_termination_fails_closed() -> None:
    result = A1SafetyPolicyAdapter(InconsistentA1Evaluator()).assess(
        Question(text="test question", metadata={"a1_safety_signals": {"topic": "hypertension"}})
    )
    assert result.decision is SafetyDecision.UNKNOWN


class CountingEmptyRetriever:
    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, question, search_plan, retrieval_request):
        del question, search_plan, retrieval_request
        self.calls += 1
        return RetrievalResult(evidence=[], tool_name="should_not_run")


def test_broken_a1_evaluator_refuses_before_retrieval() -> None:
    config = load_runtime_config()
    retriever = CountingEmptyRetriever()
    workflow = A5Workflow(
        retriever=retriever,
        claim_generator=MockClaimGenerator(),
        claim_verifier=RuleBasedClaimVerifier(config.gates.gate5),
        safety_policy=A1SafetyPolicyAdapter(BrokenA1Evaluator()),
        runtime_config=config,
    )
    run = workflow.answer(Question(text="test question"))
    assert run.decision is Decision.REFUSE
    assert retriever.calls == 0


def mock_a2_evidence(**changes: object) -> dict[str, object]:
    explicit_mock = bool(changes.pop("mock", True))
    payload: dict[str, object] = {
        "schema_version": "a2-evidence-v1",
        "id": "MOCK-A2-E1",
        "source_type": "guideline",
        "title": "[MOCK] Adapter contract evidence",
        "abstract_or_chunk": "Mock-only text for testing adapter control flow.",
        "authors": [],
        "published_at": None,
        "url": None,
        "pmid": None,
        "doi": None,
        "nct_id": None,
        "guideline_name": None,
        "page": None,
        "evidence_level": "guideline",
        "population": "synthetic population",
        "intervention": None,
        "comparator": None,
        "outcome": None,
        "fetched_at": "2026-08-11T00:00:00Z",
        "content_hash": "0" * 64,
        "source_metadata": {"mock": explicit_mock},
    }
    payload.update(changes)
    return payload


def test_a2_provisional_schema_and_gate1_fail_closed() -> None:
    schema = A2EvidencePayload.model_json_schema()
    assert schema["additionalProperties"] is False
    frozen_v1_fields = {
        "schema_version",
        "id",
        "source_type",
        "title",
        "abstract_or_chunk",
        "authors",
        "published_at",
        "url",
        "pmid",
        "doi",
        "nct_id",
        "guideline_name",
        "page",
        "evidence_level",
        "population",
        "intervention",
        "comparator",
        "outcome",
        "fetched_at",
        "content_hash",
        "source_metadata",
        "mock",
    }
    assert frozen_v1_fields == set(schema["properties"])
    with pytest.raises(UpstreamContractError, match="Gate1 missing"):
        A2EvidenceAdapter().adapt(
            mock_a2_evidence(id="REAL-LIKE-1", title="Real-like record", mock=False)
        )
    accepted = A2EvidenceAdapter(allow_mock=True).adapt(mock_a2_evidence())
    assert accepted.mock is True
    assert accepted.source_metadata["source_integrity"] == "mock_fixture"


def test_a2_mock_identifiers_are_rejected() -> None:
    # A verified public identifier is deliberately injected into a mock record;
    # construction must fail before it can be mistaken for fixture evidence.
    with pytest.raises(UpstreamContractError, match="must not carry"):
        A2EvidenceAdapter(allow_mock=True).adapt(mock_a2_evidence(pmid="31452104"))


def test_a2_formal_top_level_mock_is_accepted_without_external_identity() -> None:
    payload = mock_a2_evidence()
    payload["source_metadata"] = {}
    payload["mock"] = True
    assert A2EvidenceAdapter(allow_mock=True).adapt(payload).mock is True
    payload["url"] = "https://pubmed.ncbi.nlm.nih.gov/31452104/"
    with pytest.raises(UpstreamContractError, match="must not carry"):
        A2EvidenceAdapter(allow_mock=True).adapt(payload)


class FakeMCPClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, dict(arguments)))
        return self.response


def test_a2_mcp_adapter_routes_tool_and_quarantines_invalid_items() -> None:
    client = FakeMCPClient(
        {
            "schema_version": "a2-evidence-v1",
            "ok": True,
            "evidence": [mock_a2_evidence(), {"id": "broken"}],
            "diagnostics": {"tool_name": "search_guidelines", "source": "guideline"},
            "error": None,
            "result": None,
        }
    )
    adapter = A2MCPRetriever(
        client,
        evidence_adapter=A2EvidenceAdapter(allow_mock=True),
    )
    result = adapter.retrieve(
        Question(text="contract test"),
        plan("current_guideline"),
        request("current_guideline"),
    )
    assert isinstance(adapter, EvidenceRetriever)
    assert client.calls[0][0] == "search_guidelines"
    assert client.calls[0][1] == {"queries": ["mock contract query"], "limit": 10}
    assert [item.id for item in result.evidence] == ["MOCK-A2-E1"]
    assert result.diagnostics["upstream_status"] == "ok"
    assert result.diagnostics["adapter_status"] == "partial"
    assert result.diagnostics["quarantined_items"] == ["item-1"]


def test_a2_mcp_failed_status_is_not_silently_empty() -> None:
    adapter = A2MCPRetriever(
        FakeMCPClient({"ok": False, "evidence": [], "error": {"code": "UPSTREAM_UNAVAILABLE"}})
    )
    with pytest.raises(UpstreamRetrievalError, match="failed"):
        adapter.retrieve(Question(text="contract test"), plan(), request())


def a3_mock_evidence(**changes: object) -> dict[str, object]:
    payload = A2ToA3EvidenceAdapter().adapt(mock_a2_evidence())
    payload.update(changes)
    return payload


def test_a2_to_a3_adapter_preserves_hash_as_upstream_provenance() -> None:
    mapped = A2ToA3EvidenceAdapter().adapt(mock_a2_evidence())
    assert mapped["provenance"]["a2_content_hash"] == "0" * 64
    assert mapped["mock"] is True
    assert "schema_version" not in mapped


def test_a3_adapter_uses_only_real_spans_and_preserves_locators() -> None:
    evidence = a3_mock_evidence(source_type="pubmed", evidence_level="systematic_review")
    first_text = "Mock span one."
    second_text = "Mock span two."
    chunks = [
        {
            "chunk_id": "MOCK-CHUNK-1",
            "evidence_id": "MOCK-A2-E1",
            "evidence_content_hash": "a3-evidence-hash",
            "text": first_text,
            "page": 7,
            "raw_page": "7",
            "section": "Methods",
            "offset_scope": "document",
            "char_start": 0,
            "char_end": len(first_text),
            "token_count": 3,
            "content_hash": "chunk-hash-1",
        },
        {
            "chunk_id": "MOCK-CHUNK-2",
            "evidence_id": "MOCK-A2-E1",
            "evidence_content_hash": "a3-evidence-hash",
            "text": second_text,
            "page": None,
            "raw_page": "appendix-A",
            "section": None,
            "offset_scope": "document",
            "char_start": len(first_text),
            "char_end": len(first_text) + len(second_text),
            "token_count": 3,
            "content_hash": "chunk-hash-2",
        },
    ]
    no_spans = A3EvidenceAdapter().adapt(evidence, chunks)
    assert no_spans.spans == []
    spans = [
        {
            "span_id": "MOCK-SPAN-1",
            "evidence_id": "MOCK-A2-E1",
            "chunk_id": "MOCK-CHUNK-1",
            "text": first_text,
            "char_start": 0,
            "char_end": len(first_text),
            "offset_scope": "chunk",
            "document_char_start": 0,
            "document_char_end": len(first_text),
            "page": 7,
            "raw_page": "7",
            "section": "Methods",
            "chunk_content_hash": "chunk-hash-1",
            "evidence_content_hash": "a3-evidence-hash",
            "content_hash": "span-hash-1",
        }
    ]
    record = A3EvidenceAdapter().adapt(evidence, chunks, spans)
    assert [span.span_id for span in record.spans] == ["MOCK-SPAN-1"]
    assert record.spans[0].page == 7
    assert record.spans[0].section == "Methods"
    assert record.spans[0].char_end == len(first_text)


def test_a3_fixture_without_explicit_mock_is_rejected() -> None:
    with pytest.raises(UpstreamContractError, match="mock=true"):
        A3EvidenceAdapter().adapt(a3_mock_evidence(mock=False))
    with pytest.raises(UpstreamContractError, match="must not carry"):
        A3EvidenceAdapter().adapt(a3_mock_evidence(nct_id="NCT_FIXTURE_001"))


def a4_chunk(evidence_id: str, chunk_id: str, source: str, **changes: object) -> object:
    values: dict[str, object] = {
        "chunk_id": chunk_id,
        "evidence_id": evidence_id,
        "stable_id": f"mock:{evidence_id}",
        "text": f"Mock selected text for {chunk_id}.",
        "title": f"[MOCK] {evidence_id}",
        "source_type": source,
        "url": "",
        "published_at": "2026-01-01",
        "evidence_level": "guideline" if source == "guideline" else "systematic_review",
        "topic": "hypertension",
        "pico_population": ("synthetic adults",),
        "pico_intervention": (),
        "pico_comparator": (),
        "pico_outcome": ("synthetic outcome",),
        "content_hash": "mock-content-hash",
        "evidence_content_hash": "mock-evidence-hash",
        "fetched_at": "2026-08-11T00:00:00Z",
        "page": "2",
        "section": "Mock section",
        "mock": True,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def rank_log(chunk: object, score: object, rank: int) -> object:
    candidate = SimpleNamespace(chunk=chunk, rerank_score=score, feature_scores={"semantic": score})
    return SimpleNamespace(
        candidate=candidate,
        feature_scores={"semantic": score},
        final_rank=rank,
        selected=True,
    )


class FakeA4Service:
    def __init__(self, result: object) -> None:
        self.result = result
        self.queries: list[object] = []

    def search(self, query: object) -> object:
        self.queries.append(query)
        return self.result


def a4_result(status: str = "partial") -> object:
    first = a4_chunk("MOCK-A4-E1", "MOCK-A4-C1", "guideline")
    second = a4_chunk("MOCK-A4-E2", "MOCK-A4-C2", "pubmed")
    support = SimpleNamespace(
        claim_index=0,
        decision="supported",
        evidence_ids=("MOCK-A4-E1",),
        reason="token overlap diagnostic",
    )
    return SimpleNamespace(
        query_id="q1",
        index_version="mock-index-v1",
        corpus_version="mock-corpus-v1",
        rerank_config_version="mock-rerank-v1",
        status=status,
        selected_chunks=(first, second),
        rank_log=(rank_log(first, 0.91, 1), rank_log(second, 0.81, 2)),
        degradation_reasons=("vector_unavailable",),
        latency_ms=4,
        stage_latency_ms={"bm25": 1, "total": 4},
        retrieval_warning="partial fixture result",
        claim_support=(support,),
        conflicts=(("MOCK-A4-E1", "MOCK-A4-E2", "mock conflict"),),
    )


def test_a4_adapter_preserves_status_rank_versions_spans_and_conflicts() -> None:
    service = FakeA4Service(a4_result())
    span = {
        "span_id": "MOCK-A4-S1",
        "evidence_id": "MOCK-A4-E1",
        "chunk_id": "MOCK-A4-C1",
        "text": "Mock selected text for MOCK-A4-C1.",
        "char_start": 0,
        "char_end": len("Mock selected text for MOCK-A4-C1."),
        "offset_scope": "chunk",
        "document_char_start": 0,
        "document_char_end": len("Mock selected text for MOCK-A4-C1."),
        "page": 2,
        "raw_page": "2",
        "section": "Mock section",
        "chunk_content_hash": "mock-content-hash",
        "evidence_content_hash": "mock-evidence-hash",
        "content_hash": "mock-span-hash",
    }
    adapter = A4RAGRetriever(
        service,
        allow_mock=True,
        span_provider=lambda chunk_id: [span] if chunk_id == "MOCK-A4-C1" else [],
    )
    question = Question(
        question_id="DEV-HTN-01",
        text="contract test question",
        metadata={
            "question_type": "guideline_treatment",
            "topic": "hypertension",
            "language": "zh-CN",
            "as_of_date": "2026-08-11",
        },
    )
    result = adapter.retrieve(
        question,
        plan("current_guideline"),
        request("current_guideline"),
    )
    assert isinstance(adapter, EvidenceRetriever)
    assert service.queries[0]["question_type"] == "guideline"
    assert service.queries[0]["freshness"] == "current"
    assert service.queries[0]["topic"] == "therapy"
    assert service.queries[0]["source_types"] == ("guideline",)
    assert result.diagnostics["search_status"] == "partial"
    assert result.diagnostics["claim_support_usage"] == "diagnostic_only_never_gate5"
    assert result.diagnostics["query_snapshot"]["as_of_date"] == "2026-08-11"
    assert result.evidence[0].retrieval_score is None
    assert result.evidence[0].source_metadata["ranking_score"] == pytest.approx(0.91)
    assert result.evidence[0].spans[0].span_id == "MOCK-A4-S1"
    assert result.evidence[0].retrieval_score_kind.value == "UNKNOWN"
    assert result.evidence[0].retrieval_score_scope.value == "UNKNOWN"
    assert result.evidence[0].retrieval_score_calibrated is None
    assert result.evidence[0].conflicts_with_ids == ["MOCK-A4-E2"]
    assert result.evidence[0].source_metadata["index_version"] == "mock-index-v1"
    assert result.evidence[0].source_metadata.get("verification_status") is None


def test_a4_unknown_score_stays_none_and_failed_status_raises() -> None:
    payload = a4_result(status="ok")
    payload.rank_log = (rank_log(payload.selected_chunks[0], 4.2, 1),)
    payload.selected_chunks = (payload.selected_chunks[0],)
    payload.conflicts = ()
    record = A4RAGRetriever(FakeA4Service(payload), allow_mock=True).retrieve(
        Question(text="contract test"), plan(), request()
    ).evidence[0]
    assert record.retrieval_score is None
    assert record.spans == []

    failed = a4_result(status="failed")
    with pytest.raises(UpstreamRetrievalError, match="failed"):
        A4RAGRetriever(FakeA4Service(failed), allow_mock=True).retrieve(
            Question(text="contract test"), plan(), request()
        )


def test_a4_explicit_quality_score_is_separate_from_query_local_ranking() -> None:
    payload = a4_result(status="ok")
    payload.conflicts = ()
    payload.quality_scores = {"MOCK-A4-C1": 0.83, "MOCK-A4-C2": 0.79}
    payload.quality_score_kind = "QUALITY"
    payload.quality_score_scope = "CROSS_QUERY"
    payload.quality_score_calibrated = True
    records = A4RAGRetriever(FakeA4Service(payload), allow_mock=True).retrieve(
        Question(text="contract test"), plan(), request()
    ).evidence
    assert records[0].retrieval_score == pytest.approx(0.83)
    assert records[0].source_metadata["ranking_score"] == pytest.approx(0.91)
    assert records[0].retrieval_score_kind.value == "QUALITY"
    assert records[0].retrieval_score_scope.value == "CROSS_QUERY"
    assert records[0].retrieval_score_calibrated is True


def test_a4_production_mapping_enforces_gate1_provenance() -> None:
    payload = a4_result(status="ok")
    payload.selected_chunks = (
        a4_chunk(
            "REAL-LIKE-E1",
            "REAL-LIKE-C1",
            "pubmed",
            stable_id="source-id-present",
            title="Real-like but incomplete record",
            mock=False,
        ),
    )
    payload.rank_log = (rank_log(payload.selected_chunks[0], 0.9, 1),)
    payload.conflicts = ()
    with pytest.raises(UpstreamContractError, match="Gate1 missing"):
        A4RAGRetriever(FakeA4Service(payload)).retrieve(
            Question(text="contract test"), plan(), request()
        )


def test_a4_result_requires_reproducibility_versions() -> None:
    payload = a4_result(status="empty")
    payload.index_version = ""
    payload.selected_chunks = ()
    payload.rank_log = ()
    payload.conflicts = ()
    with pytest.raises(UpstreamContractError, match="version fields"):
        A4RAGRetriever(FakeA4Service(payload), allow_mock=True).retrieve(
            Question(text="contract test"), plan(), request()
        )


def test_a4_unverified_embedding_and_cross_encoder_are_blocked_by_capability_config() -> None:
    payload = a4_result(status="ok")
    production = a4_chunk(
        "PMID:31452104",
        "PMID:31452104#chunk-1",
        "pubmed",
        stable_id="PMID:31452104",
        title="Molegro Virtual Docker for Docking.",
        url="https://pubmed.ncbi.nlm.nih.gov/31452104/",
        pmid="31452104",
        mock=False,
        embedding_model="BAAI/bge-m3",
    )
    payload.selected_chunks = (production,)
    payload.rank_log = (rank_log(production, 0.9, 1),)
    payload.conflicts = ()
    with pytest.raises(UpstreamContractError, match="unapproved_embedding_model"):
        A4RAGRetriever(FakeA4Service(payload)).retrieve(
            Question(text="contract test"), plan(), request()
        )

    mock_payload = a4_result(status="ok")
    mock_payload.rank_log[0].feature_scores["cross_encoder"] = 8.2
    with pytest.raises(UpstreamContractError, match="unapproved_cross_encoder"):
        A4RAGRetriever(FakeA4Service(mock_payload), allow_mock=True).retrieve(
            Question(text="contract test"), plan(), request()
        )


def test_runtime_snapshot_records_provisional_contract_versions() -> None:
    config = load_runtime_config()
    snapshot = config.snapshot()
    assert snapshot.integrations["config_version"] == "a5-upstream-adapters-v0.3.0"
    assert snapshot.integrations["a2"]["status"] == "reviewed_branch_contract"
