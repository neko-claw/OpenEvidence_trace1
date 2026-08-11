from __future__ import annotations

from time import perf_counter
from typing import Any, Protocol

from a2.adapters.a5_evidence import to_a5_evidence
from a2.models.errors import A2Exception
from a2.models.evidence import A2_EVIDENCE_SCHEMA_VERSION, A2Evidence
from a2.storage.dedup import canonical_key
from a5.domain.models import Question, RetrievalRequest, RetrievalResult, SearchPlan


class MCPClientPort(Protocol):
    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


ROUTES = {
    "pubmed": "search_pubmed",
    "europe_pmc": "search_europe_pmc",
    "clinical_trials": "search_trials",
    "trials": "search_trials",
    "guideline": "search_guidelines",
    "guidelines": "search_guidelines",
}


class A2MCPRetriever:
    """A5 EvidenceRetriever adapter; each retrieve is exactly one MCP call."""

    def __init__(
        self, client: MCPClientPort, *, result_limit: int = 10,
        config_version: str | None = None, mcp_sdk_version: str | None = None,
    ) -> None:
        self.client = client
        self.result_limit = result_limit
        self.config_version = config_version
        self.mcp_sdk_version = mcp_sdk_version

    def retrieve(self, question: Question, plan: SearchPlan, request: RetrievalRequest) -> RetrievalResult:
        del question
        started = perf_counter()
        source = request.source_type.lower()
        tool_name = ROUTES.get(source)
        base = {
            "adapter": type(self).__name__, "source": source,
            "tool_name": tool_name, "tool_call_index": request.tool_call_index,
            "query_count": len(plan.queries), "result_count": 0,
            "cache_hit": None, "latency_ms": 0.0,
            "a2_schema_version": A2_EVIDENCE_SCHEMA_VERSION,
            "a2_config_version": self.config_version,
            "mcp_sdk_version": self.mcp_sdk_version,
            "effective_result_limit": self.result_limit, "error": None,
        }
        if tool_name is None:
            base["error"] = {"code": "UNSUPPORTED_SOURCE", "message": f"unsupported A2 source route: {source}", "retryable": False}
            base["latency_ms"] = (perf_counter() - started) * 1000
            return RetrievalResult(evidence=[], tool_name="unsupported_source", diagnostics=base)
        try:
            envelope = self.client.call_tool(tool_name, {"queries": list(plan.queries), "limit": self.result_limit})
        except A2Exception as exc:
            base["error"] = exc.error.model_dump(mode="json")
            base["latency_ms"] = (perf_counter() - started) * 1000
            return RetrievalResult(evidence=[], tool_name=tool_name, diagnostics=base)
        except TimeoutError:
            base["error"] = {"code": "MCP_ERROR", "message": "MCP tool call timed out", "retryable": True}
            base["latency_ms"] = (perf_counter() - started) * 1000
            return RetrievalResult(evidence=[], tool_name=tool_name, diagnostics=base)
        if not envelope.get("ok"):
            base["error"] = envelope.get("error")
            base.update(_safe_diagnostics(envelope.get("diagnostics", {})))
            base["latency_ms"] = (perf_counter() - started) * 1000
            return RetrievalResult(evidence=[], tool_name=tool_name, diagnostics=base)
        unique: dict[str, A2Evidence] = {}
        for item in envelope.get("evidence", []):
            record = A2Evidence.model_validate(item)
            unique.setdefault(canonical_key(record), record)
        evidence = [to_a5_evidence(record) for record in unique.values()]
        base.update(_safe_diagnostics(envelope.get("diagnostics", {})))
        base["tool_name"] = tool_name
        base["tool_call_index"] = request.tool_call_index
        base["query_count"] = len(plan.queries)
        base["result_count"] = len(evidence)
        base["latency_ms"] = (perf_counter() - started) * 1000
        return RetrievalResult(evidence=evidence, tool_name=tool_name, diagnostics=base)


def _safe_diagnostics(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {"cache_hit", "result_count", "upstream_request_count", "retry_count", "upstream_api_version"}
    return {key: value.get(key) for key in allowed if key in value}
