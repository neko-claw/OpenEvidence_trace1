from a5.adapters.mock_evidence_retriever import MockEvidenceRetriever
from a5.domain.models import Question, SearchPlan
from a5.ports.evidence_retriever import EvidenceRetriever


def make_plan() -> SearchPlan:
    return SearchPlan(
        queries=["artificial query"],
        preferred_sources=["mock"],
        freshness_required=False,
        expected_evidence_types=["mock"],
        max_tool_calls=1,
    )


def test_mock_retriever_returns_only_requested_mock_records() -> None:
    adapter = MockEvidenceRetriever()
    result = adapter.retrieve(
        Question(text="fixture", metadata={"fixture_evidence_ids": ["E1", "E3"]}),
        make_plan(),
    )

    assert [record.id for record in result.evidence] == ["E1", "E3"]
    assert all(record.mock for record in result.evidence)
    assert result.tool_name == "mock_search"


def test_mock_retriever_satisfies_port_without_core_coupling() -> None:
    assert isinstance(MockEvidenceRetriever(), EvidenceRetriever)


def test_mock_retriever_can_return_empty_result() -> None:
    result = MockEvidenceRetriever().retrieve(
        Question(text="fixture", metadata={"fixture_evidence_ids": []}),
        make_plan(),
    )
    assert result.evidence == []
