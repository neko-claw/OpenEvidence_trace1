from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from a2.config import load_a2_config
from a2.mcp.client import A2MCPClient
from a2.mcp.server import build_mcp_server, build_service
from a2.mcp.tools import A2ToolService
from a2.models.evidence import A2Evidence, SourceType
from a2.storage.dedup import compute_content_hash
from a2.storage.sqlite_store import SQLiteStore


class _RecordedPublicConnector:
    """Minimal recorded public-record fixture; never presented as live evidence."""

    def search(self, query: str, limit: int = 10) -> list[A2Evidence]:
        del query
        data = {
            "id": "PMID:31452104", "source_type": SourceType.PUBMED,
            "title": "Molegro Virtual Docker for Docking.",
            "abstract_or_chunk": "Molegro Virtual Docker is a protein-ligand docking simulation program.",
            "pmid": "31452104", "doi": "10.1007/978-1-4939-9752-7_10",
            "url": "https://pubmed.ncbi.nlm.nih.gov/31452104/",
            "source_metadata": {"fixture": "recorded_public_subset", "not_live_verified": True},
        }
        data["content_hash"] = compute_content_hash(data)
        return [A2Evidence.model_validate(data)][:limit]

    def get(self, *args: str) -> A2Evidence:
        return self.search("", 1)[0]


def offline_smoke() -> dict:
    """Run a deterministic in-process MCP request without network access."""
    with TemporaryDirectory(prefix="a2-smoke-") as directory:
        connector = _RecordedPublicConnector()
        service = A2ToolService(
            store=SQLiteStore(Path(directory) / "a2.sqlite3"), pubmed=connector,
            europe_pmc=connector, clinical_trials=connector, guidelines=connector,
        )
        client = A2MCPClient(build_mcp_server(service))
        first = client.call_tool("search_pubmed", {"queries": ["Molegro Virtual Docker"], "limit": 1})
        second = client.call_tool("get_evidence", {"evidence_id": "PMID:31452104"})
        return {
            "source": "pubmed", "tool_name": "search_pubmed",
            "result_count": len(first["evidence"]),
            "cache_hit": second["diagnostics"]["cache_hit"],
            "evidence_id": first["evidence"][0]["id"],
        }


def live_smoke() -> dict:
    """Run one opt-in live PubMed call through the same MCP abstraction."""
    config = load_a2_config()
    client = A2MCPClient(build_mcp_server(build_service(config)))
    result = client.call_tool("search_pubmed", {"queries": ["Molegro Virtual Docker"], "limit": 1})
    return {"source": "pubmed", "tool_name": "search_pubmed", "result_count": len(result["evidence"]), "cache_hit": result["diagnostics"]["cache_hit"], "evidence_id": result["evidence"][0]["id"] if result["evidence"] else None}


def main() -> None:
    result = live_smoke() if os.getenv("A2_LIVE_TESTS") == "1" else offline_smoke()
    for key in ("source", "tool_name", "result_count", "cache_hit", "evidence_id"):
        print(f"{key}={result[key]}")


if __name__ == "__main__":
    main()
