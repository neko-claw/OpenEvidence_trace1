from __future__ import annotations

from datetime import datetime, timezone

import pytest

from a2.adapters.a5_evidence import to_a5_evidence
from a2.adapters.a5_retriever import A2MCPRetriever
from a2.mcp.client import A2MCPClient
from a2.mcp.server import build_mcp_server
from a2.mcp.tools import A2ToolService
from a2.models.errors import A2Error, A2ErrorCode, A2Exception
from a2.models.evidence import A2Evidence, SourceType
from a2.storage.dedup import compute_content_hash
from a2.storage.sqlite_store import SQLiteStore
from a5.adapters.default_safety_policy import FixtureSafetyPolicy
from a5.adapters.mock_claim_generator import MockClaimGenerator
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.agent.workflow import A5Workflow
from a5.domain.enums import Decision
from a5.domain.models import AgentPlan, Question, RetrievalRequest, SearchPlan
from a5.ports.evidence_retriever import EvidenceRetriever
from a5.runtime_config import load_runtime_config
from a5.skills.evidence_research import EvidenceResearchSkill


def public_record(source_type: SourceType = SourceType.PUBMED, **updates) -> A2Evidence:
    data = {
        "id": "PMID:31452104", "source_type": source_type,
        "title": "Molegro Virtual Docker for Docking.",
        "abstract_or_chunk": "Molegro Virtual Docker is a protein-ligand docking simulation program.",
        "authors": ["Gabriela Bitencourt-Ferreira", "Walter Filgueira de Azevedo"],
        "published_at": datetime(2019, 1, 1, tzinfo=timezone.utc),
        "url": "https://pubmed.ncbi.nlm.nih.gov/31452104/", "pmid": "31452104",
        "doi": "10.1007/978-1-4939-9752-7_10",
    }
    data.update(updates); data["content_hash"] = compute_content_hash(data)
    return A2Evidence.model_validate(data)


class FixtureConnector:
    def __init__(self, records=None, error: A2Exception | None = None) -> None:
        self.records = records if records is not None else [public_record()]
        self.error = error
        self.calls = 0

    def search(self, query: str, limit: int = 10):
        self.calls += 1
        if self.error: raise self.error
        return self.records[:limit]

    def get(self, *args):
        if self.error: raise self.error
        return self.records[0]


def stack(tmp_path, connector: FixtureConnector | None = None):
    source = connector or FixtureConnector()
    service = A2ToolService(store=SQLiteStore(tmp_path / "a2.sqlite3"), pubmed=source, europe_pmc=source, clinical_trials=source, guidelines=source)
    client = A2MCPClient(build_mcp_server(service))
    return source, service, client


def plan() -> SearchPlan:
    return SearchPlan(queries=["Molegro Virtual Docker"], preferred_sources=["pubmed"], freshness_required=False, expected_evidence_types=["primary_study"], max_tool_calls=1)


def test_a2_to_a5_mapping_preserves_unknowns_metadata_and_no_span() -> None:
    record = public_record(population=None, evidence_level=None)
    mapped = to_a5_evidence(record)
    assert mapped.id == record.id and mapped.content == record.abstract_or_chunk
    assert mapped.population is None and mapped.evidence_level is None
    assert mapped.retrieval_score is None and mapped.spans == [] and mapped.mock is False
    assert mapped.source_metadata["pmid"] == "31452104"
    assert mapped.source_metadata["content_hash"] == record.content_hash


def test_mcp_discovery_schemas_call_serialization_cache_unknown_and_invalid(tmp_path) -> None:
    source, _, client = stack(tmp_path)
    tools = {item["name"]: item for item in client.list_tools()}
    assert set(tools) == {"search_pubmed", "search_europe_pmc", "search_trials", "search_guidelines", "get_evidence", "validate_citation"}
    assert tools["search_pubmed"]["input_schema"]["properties"]["queries"]["type"] == "array"
    result = client.call_tool("search_pubmed", {"queries": ["Molegro Virtual Docker"], "limit": 1})
    assert result["ok"] and A2Evidence.model_validate(result["evidence"][0]).id == "PMID:31452104"
    assert source.calls == 1
    local = client.call_tool("get_evidence", {"evidence_id": "PMID:31452104"})
    assert local["diagnostics"]["cache_hit"] is True
    valid = client.call_tool("validate_citation", {"evidence_id": "PMID:31452104"})
    unknown = client.call_tool("validate_citation", {"evidence_id": "PMID:30491001"})
    invalid = client.call_tool("validate_citation", {"evidence_id": "not-an-evidence-id"})
    assert valid["result"]["status"] == "VALID"
    assert unknown["result"]["status"] == "UNKNOWN" and unknown["result"]["valid"] is None
    assert invalid["result"]["status"] == "INVALID"


def test_mcp_empty_and_structured_error(tmp_path) -> None:
    _, _, empty_client = stack(tmp_path / "empty", FixtureConnector([]))
    assert empty_client.call_tool("search_pubmed", {"queries": ["none"], "limit": 1})["evidence"] == []
    failure = A2Exception(A2Error(code=A2ErrorCode.TIMEOUT, source="pubmed", message="PubMed request failed", retryable=True))
    _, _, error_client = stack(tmp_path / "error", FixtureConnector(error=failure))
    response = error_client.call_tool("search_pubmed", {"queries": ["timeout"], "limit": 1})
    assert response["ok"] is False and response["error"]["code"] == "TIMEOUT"


@pytest.mark.parametrize(("source", "tool"), [("pubmed", "search_pubmed"), ("europe_pmc", "search_europe_pmc"), ("clinical_trials", "search_trials"), ("trials", "search_trials"), ("guideline", "search_guidelines"), ("guidelines", "search_guidelines")])
def test_retriever_routes_one_mcp_call_and_diagnostics(tmp_path, source, tool) -> None:
    connector, _, client = stack(tmp_path / source)
    retriever = A2MCPRetriever(client, result_limit=1)
    result = retriever.retrieve(Question(text="fixture"), plan(), RetrievalRequest(source_type=source, tool_call_index=3))
    assert result.tool_name == tool and result.diagnostics["tool_call_index"] == 3
    assert result.diagnostics["query_count"] == 1 and result.diagnostics["result_count"] == 1
    assert connector.calls == 1 and isinstance(retriever, EvidenceRetriever)


def test_retriever_unknown_empty_mcp_error_and_duplicate(tmp_path) -> None:
    _, _, client = stack(tmp_path / "ok", FixtureConnector([]))
    retriever = A2MCPRetriever(client)
    unknown = retriever.retrieve(Question(text="x"), plan(), RetrievalRequest(source_type="unknown", tool_call_index=1))
    empty = retriever.retrieve(Question(text="x"), plan(), RetrievalRequest(source_type="pubmed", tool_call_index=2))
    assert unknown.evidence == [] and unknown.diagnostics["error"]["code"] == "UNSUPPORTED_SOURCE"
    assert empty.evidence == []
    duplicate_connector = FixtureConnector([public_record(), public_record(id="EPMC:MED:31452104", source_type=SourceType.EUROPE_PMC)])
    _, _, duplicate_client = stack(tmp_path / "duplicate", duplicate_connector)
    deduped = A2MCPRetriever(duplicate_client).retrieve(Question(text="x"), plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1))
    assert len(deduped.evidence) == 1
    class BrokenClient:
        def call_tool(self, name, arguments):
            raise A2Exception(A2Error(code=A2ErrorCode.MCP_ERROR, message="safe MCP failure"))
    failed = A2MCPRetriever(BrokenClient()).retrieve(Question(text="x"), plan(), RetrievalRequest(source_type="pubmed", tool_call_index=1))
    assert failed.evidence == [] and failed.diagnostics["error"]["code"] == "MCP_ERROR"


class PubMedOnlySkill(EvidenceResearchSkill):
    def plan(self, question):
        return AgentPlan(question_type="treatment_evidence", selected_skill="evidence_research", search_plan=SearchPlan(queries=[question.text], preferred_sources=["pubmed"], freshness_required=False, expected_evidence_types=["primary_study"], max_tool_calls=1), policy_version="test")


def test_a5_full_offline_path_through_mcp_fixture_and_fail_closed_gate(tmp_path) -> None:
    _, _, client = stack(tmp_path)
    config = load_runtime_config()
    workflow = A5Workflow(
        retriever=A2MCPRetriever(client, result_limit=1), claim_generator=MockClaimGenerator(),
        claim_verifier=RuleBasedClaimVerifier(config.gates.gate5), safety_policy=FixtureSafetyPolicy(),
        runtime_config=config, research_skill=PubMedOnlySkill(config),
    )
    run = workflow.answer(Question(text="Molegro Virtual Docker", metadata={"mock_safety_decision": "ALLOW"}))
    assert run.retrieved_evidence[0].id == "PMID:31452104"
    assert run.retrieved_evidence[0].mock is False
    assert run.decision is Decision.REFUSE  # A4 score/A3 level are absent, so Gate2 fails closed.
    retrieve = next(event for event in run.trace if event.tool == "search_pubmed")
    assert retrieve.details["diagnostics"]["a2_schema_version"] == "a2-evidence-v1"
