from __future__ import annotations

from time import perf_counter
from typing import Any, Protocol

from a2.models.errors import A2Error, A2ErrorCode, A2Exception
from a2.models.evidence import A2Evidence
from a2.models.tool_response import ToolDiagnostics, ToolResponse
from a2.storage.dedup import canonical_key
from a2.storage.sqlite_store import SQLiteStore


class SearchConnector(Protocol):
    def search(self, query: str, limit: int = 10) -> list[A2Evidence]: ...


class A2ToolService:
    """Read-only MCP tool application service over source connectors and store."""

    def __init__(
        self, *, store: SQLiteStore, pubmed: Any, europe_pmc: Any,
        clinical_trials: Any, guidelines: Any, max_queries: int = 8,
        max_query_length: int = 500, max_result_limit: int = 50,
        diagnostic_context: dict[str, Any] | None = None,
    ) -> None:
        self.store = store
        self.connectors = {
            "pubmed": pubmed, "europe_pmc": europe_pmc,
            "clinical_trials": clinical_trials, "guideline": guidelines,
        }
        self.max_queries = max_queries
        self.max_query_length = max_query_length
        self.max_result_limit = max_result_limit
        self.diagnostic_context = diagnostic_context or {}

    def search_pubmed(self, queries: list[str], limit: int = 10) -> dict[str, Any]:
        """Execute the PubMed MCP tool contract."""
        return self._search("search_pubmed", "pubmed", queries, limit)

    def search_europe_pmc(self, queries: list[str], limit: int = 10) -> dict[str, Any]:
        """Execute the Europe PMC MCP tool contract."""
        return self._search("search_europe_pmc", "europe_pmc", queries, limit)

    def search_trials(self, queries: list[str], limit: int = 10) -> dict[str, Any]:
        """Execute the ClinicalTrials MCP tool contract."""
        return self._search("search_trials", "clinical_trials", queries, limit)

    def search_guidelines(self, queries: list[str], limit: int = 10) -> dict[str, Any]:
        """Execute the approved-guidelines MCP tool contract."""
        return self._search("search_guidelines", "guideline", queries, limit)

    def _search(self, tool_name: str, source: str, queries: list[str], limit: int) -> dict[str, Any]:
        started = perf_counter()
        try:
            self._validate_search(queries, limit)
            connector = self.connectors[source]
            before = _http_stats(connector)
            by_key: dict[str, A2Evidence] = {}
            for query in queries:
                remaining = limit - len(by_key)
                if remaining <= 0:
                    break
                for record in connector.search(query.strip(), remaining):
                    persisted = self.store.put(record)
                    by_key[canonical_key(persisted)] = persisted
            after = _http_stats(connector)
            evidence = list(by_key.values())[:limit]
            return ToolResponse(
                ok=True, evidence=evidence,
                diagnostics=ToolDiagnostics(
                    tool_name=tool_name, source=source,
                    cache_hit=after[2] > before[2], result_count=len(evidence),
                    upstream_request_count=after[0] - before[0], retry_count=after[1] - before[1],
                    latency_ms=(perf_counter() - started) * 1000,
                    upstream_api_version="v2" if source == "clinical_trials" else None,
                    **self.diagnostic_context,
                ),
            ).model_dump(mode="json")
        except A2Exception as exc:
            return self._error(tool_name, source, exc.error, started)
        except (ValueError, TypeError) as exc:
            return self._error(tool_name, source, A2Error(code=A2ErrorCode.INVALID_REQUEST, source=source, message=str(exc)), started)

    def get_evidence(self, evidence_id: str, allow_live_lookup: bool = False) -> dict[str, Any]:
        """Get exact evidence locally or via explicit exact live lookup."""
        started = perf_counter()
        local = self.store.get(evidence_id)
        if local:
            return ToolResponse(ok=True, evidence=[local], diagnostics=ToolDiagnostics(tool_name="get_evidence", source=local.source_type.value, cache_hit=True, result_count=1, latency_ms=(perf_counter() - started) * 1000)).model_dump(mode="json")
        if not allow_live_lookup:
            return self._error("get_evidence", _namespace(evidence_id), A2Error(code=A2ErrorCode.NOT_FOUND, source=_namespace(evidence_id), message="evidence is not present in the local store"), started)
        try:
            record = self._live_get(evidence_id)
            record = self.store.put(record)
            return ToolResponse(ok=True, evidence=[record], diagnostics=ToolDiagnostics(tool_name="get_evidence", source=record.source_type.value, cache_hit=False, result_count=1, upstream_request_count=1, latency_ms=(perf_counter() - started) * 1000)).model_dump(mode="json")
        except A2Exception as exc:
            return self._error("get_evidence", _namespace(evidence_id), exc.error, started)

    def validate_citation(self, evidence_id: str, allow_live_lookup: bool = False) -> dict[str, Any]:
        """Return fail-closed VALID, INVALID, or UNKNOWN citation status."""
        started = perf_counter()
        source = _namespace(evidence_id)
        local = self.store.get(evidence_id)
        if local:
            result = {"valid": True, "status": "VALID", "evidence_id": evidence_id, "source": local.source_type.value, "reason": "native identifier is present in the local evidence store"}
            return ToolResponse(ok=True, result=result, diagnostics=ToolDiagnostics(tool_name="validate_citation", source=local.source_type.value, cache_hit=True, result_count=1, latency_ms=(perf_counter() - started) * 1000)).model_dump(mode="json")
        if source is None:
            result = {"valid": False, "status": "INVALID", "evidence_id": evidence_id, "source": None, "reason": "unsupported or malformed evidence namespace"}
            return ToolResponse(ok=True, result=result, diagnostics=ToolDiagnostics(tool_name="validate_citation", result_count=0, latency_ms=(perf_counter() - started) * 1000)).model_dump(mode="json")
        if allow_live_lookup:
            lookup = self.get_evidence(evidence_id, allow_live_lookup=True)
            if lookup["ok"]:
                result = {"valid": True, "status": "VALID", "evidence_id": evidence_id, "source": source, "reason": "source-native identifier was confirmed by live lookup"}
            elif lookup.get("error", {}).get("code") == A2ErrorCode.NOT_FOUND.value:
                result = {"valid": False, "status": "INVALID", "evidence_id": evidence_id, "source": source, "reason": "source-native identifier was not found"}
            else:
                result = {"valid": None, "status": "UNKNOWN", "evidence_id": evidence_id, "source": source, "reason": "live source verification was unavailable"}
        else:
            result = {"valid": None, "status": "UNKNOWN", "evidence_id": evidence_id, "source": source, "reason": "identifier is well formed but absent locally; live lookup disabled"}
        return ToolResponse(ok=True, result=result, diagnostics=ToolDiagnostics(tool_name="validate_citation", source=source, cache_hit=False, result_count=0, latency_ms=(perf_counter() - started) * 1000)).model_dump(mode="json")

    def _live_get(self, evidence_id: str) -> A2Evidence:
        if evidence_id.startswith("PMID:"):
            return self.connectors["pubmed"].get(evidence_id.removeprefix("PMID:"))
        if evidence_id.startswith("NCT:"):
            return self.connectors["clinical_trials"].get(evidence_id.removeprefix("NCT:"))
        if evidence_id.startswith("EPMC:"):
            parts = evidence_id.split(":", 2)
            if len(parts) == 3:
                return self.connectors["europe_pmc"].get(parts[1], parts[2])
        if evidence_id.startswith("GUIDELINE:"):
            return self.connectors["guideline"].get(evidence_id)
        raise A2Exception(A2Error(code=A2ErrorCode.UNSUPPORTED_SOURCE, source=None, message="unsupported evidence namespace"))

    def _validate_search(self, queries: list[str], limit: int) -> None:
        if not queries or len(queries) > self.max_queries:
            raise ValueError(f"queries must contain 1..{self.max_queries} items")
        if limit < 1 or limit > self.max_result_limit:
            raise ValueError(f"limit must be within 1..{self.max_result_limit}")
        if any(not isinstance(query, str) or not query.strip() or len(query) > self.max_query_length for query in queries):
            raise ValueError(f"each query must be nonblank and at most {self.max_query_length} characters")

    def _error(self, tool_name: str, source: str | None, error: A2Error, started: float) -> dict[str, Any]:
        return ToolResponse(ok=False, error=error, diagnostics=ToolDiagnostics(tool_name=tool_name, source=source, latency_ms=(perf_counter() - started) * 1000, **self.diagnostic_context)).model_dump(mode="json")


def _http_stats(connector: Any) -> tuple[int, int, int]:
    http = getattr(connector, "http", None)
    return (getattr(http, "request_count", 0), getattr(http, "retry_count", 0), getattr(http, "cache_hits", 0))


def _namespace(evidence_id: str) -> str | None:
    if evidence_id.startswith("PMID:") and evidence_id[5:].isdigit(): return "pubmed"
    if evidence_id.startswith("NCT:NCT") and evidence_id[7:].isdigit(): return "clinical_trials"
    if evidence_id.startswith("EPMC:") and len(evidence_id.split(":")) >= 3: return "europe_pmc"
    if evidence_id.startswith("GUIDELINE:") and len(evidence_id.split(":")) == 5: return "guideline"
    return None
