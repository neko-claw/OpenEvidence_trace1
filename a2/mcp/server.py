from __future__ import annotations

import logging

from mcp.server import MCPServer

from a2.config import A2Config, load_a2_config
from a2.connectors import ClinicalTrialsConnector, EuropePMCConnector, GuidelinesConnector, PubMedConnector
from a2.connectors.base import A2HTTPClient
from a2.mcp.tools import A2ToolService
from a2.models.tool_response import ToolResponse
from a2.storage.sqlite_store import SQLiteStore


def build_service(config: A2Config | None = None) -> A2ToolService:
    """Build the production local service; live calls remain tool-invocation driven."""
    cfg = config or load_a2_config()
    store = SQLiteStore(cfg.storage.sqlite_path)
    def http(source: str) -> A2HTTPClient:
        settings = cfg.sources[source]
        return A2HTTPClient(source, cfg.http, store, float(settings.get("requests_per_second", 0)))
    return A2ToolService(
        store=store,
        pubmed=PubMedConnector(http("pubmed"), cfg.sources["pubmed"]["base_url"]),
        europe_pmc=EuropePMCConnector(http("europe_pmc"), cfg.sources["europe_pmc"]["base_url"]),
        clinical_trials=ClinicalTrialsConnector(http("clinical_trials"), cfg.sources["clinical_trials"]["base_url"]),
        guidelines=GuidelinesConnector(cfg.sources["guidelines"]["manifest_path"]),
        max_queries=cfg.max_queries, max_query_length=cfg.max_query_length,
        max_result_limit=cfg.max_result_limit,
        diagnostic_context={
            "a2_config_version": cfg.schema_version,
            "mcp_sdk_version": cfg.mcp_sdk_version,
            "http_connect_timeout_seconds": cfg.http.connect_timeout_seconds,
            "http_read_timeout_seconds": cfg.http.read_timeout_seconds,
            "http_total_timeout_seconds": cfg.http.total_timeout_seconds,
            "http_retry_count": cfg.http.retry_count,
            "default_result_limit": cfg.default_result_limit,
        },
    )


def build_mcp_server(service: A2ToolService | None = None) -> MCPServer:
    """Expose six read-only A2 tools through official MCP Python SDK v2."""
    tools = service or build_service()
    server = MCPServer("OpenEvidence A2", version="0.1.0", log_level="WARNING")

    @server.tool(structured_output=True)
    def search_pubmed(queries: list[str], limit: int = 10) -> ToolResponse:
        """Search PubMed with bounded query and result lists."""
        return ToolResponse.model_validate(tools.search_pubmed(queries, limit))

    @server.tool(structured_output=True)
    def search_europe_pmc(queries: list[str], limit: int = 10) -> ToolResponse:
        """Search Europe PMC core records."""
        return ToolResponse.model_validate(tools.search_europe_pmc(queries, limit))

    @server.tool(structured_output=True)
    def search_trials(queries: list[str], limit: int = 10) -> ToolResponse:
        """Search ClinicalTrials.gov API v2."""
        return ToolResponse.model_validate(tools.search_trials(queries, limit))

    @server.tool(structured_output=True)
    def search_guidelines(queries: list[str], limit: int = 10) -> ToolResponse:
        """Search only locally whitelisted guidelines."""
        return ToolResponse.model_validate(tools.search_guidelines(queries, limit))

    @server.tool(structured_output=True)
    def get_evidence(evidence_id: str, allow_live_lookup: bool = False) -> ToolResponse:
        """Get an exact evidence ID locally, optionally by exact native lookup."""
        return ToolResponse.model_validate(tools.get_evidence(evidence_id, allow_live_lookup))

    @server.tool(structured_output=True)
    def validate_citation(evidence_id: str, allow_live_lookup: bool = False) -> ToolResponse:
        """Validate a citation against the local store and optional exact lookup."""
        return ToolResponse.model_validate(tools.validate_citation(evidence_id, allow_live_lookup))

    return server


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    build_mcp_server().run("stdio")


if __name__ == "__main__":
    main()
