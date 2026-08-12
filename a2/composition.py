from __future__ import annotations

from a2.adapters.a5_retriever import A2MCPRetriever
from a2.config import load_a2_config
from a2.mcp.client import A2MCPClient


def build_local_a2_retriever(*, result_limit: int = 10) -> A2MCPRetriever:
    """Explicit opt-in A2 composition; A5 demo/default wiring remains unchanged."""
    config = load_a2_config()
    return A2MCPRetriever(
        A2MCPClient.local_stdio(), result_limit=result_limit,
        config_version=config.schema_version, mcp_sdk_version=config.mcp_sdk_version,
    )
