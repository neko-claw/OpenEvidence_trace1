from __future__ import annotations

import os

import pytest

from a2.mcp.client import A2MCPClient
from a2.mcp.server import build_mcp_server, build_service
from a2.models.evidence import A2Evidence


pytestmark = pytest.mark.skipif(os.getenv("A2_LIVE_TESTS") != "1", reason="set A2_LIVE_TESTS=1 for explicit network verification")


@pytest.fixture(scope="module")
def client() -> A2MCPClient:
    return A2MCPClient(build_mcp_server(build_service()))


@pytest.mark.parametrize(("tool", "query", "prefix"), [
    ("search_pubmed", "Molegro Virtual Docker", "PMID:"),
    ("search_europe_pmc", "EXT_ID:31452104 AND SRC:MED", "EPMC:"),
    ("search_trials", "NCT03036124", "NCT:"),
])
def test_live_source_schema_identifier_and_cache(client, tool, query, prefix) -> None:
    first = client.call_tool(tool, {"queries": [query], "limit": 1})
    second = client.call_tool(tool, {"queries": [query], "limit": 1})
    assert first["ok"] and first["evidence"]
    assert A2Evidence.model_validate(first["evidence"][0]).id.startswith(prefix)
    assert second["diagnostics"]["cache_hit"] is True
