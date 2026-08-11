from a5.adapters.mock_evidence_retriever import MockEvidenceRetriever
from a5.domain.models import Question, RetrievalRequest, SearchPlan
from a5.ports.evidence_retriever import EvidenceRetriever


def make_plan() -> SearchPlan:
    return SearchPlan(
        queries=["artificial query"],
        preferred_sources=["guideline"],
        freshness_required=False,
        expected_evidence_types=["guideline"],
        max_tool_calls=1,
    )


def test_mock_retriever_returns_requested_batch_and_records_call() -> None:
    adapter = MockEvidenceRetriever()
    result = adapter.retrieve(
        Question(text="fixture", metadata={"fixture_batches": [["E1", "E3"]]}),
        make_plan(),
        RetrievalRequest(source_type="guideline", tool_call_index=1),
    )
    assert [record.id for record in result.evidence] == ["E1", "E3"]
    assert all(record.mock for record in result.evidence)
    assert adapter.call_count == 1
    assert result.diagnostics["tool_call_index"] == 1


def test_mock_retriever_satisfies_port_and_can_return_empty() -> None:
    adapter = MockEvidenceRetriever()
    assert isinstance(adapter, EvidenceRetriever)
    result = adapter.retrieve(
        Question(text="fixture", metadata={"fixture_batches": [[]]}),
        make_plan(),
        RetrievalRequest(source_type="guideline", tool_call_index=1),
    )
    assert result.evidence == []
