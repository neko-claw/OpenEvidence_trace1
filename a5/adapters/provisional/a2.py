from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from a5.adapters.provisional.common import (
    UpstreamContractError,
    UpstreamRetrievalError,
    enum_text,
    fixture_like,
    parse_datetime,
    to_mapping,
)
from a5.domain.models import (
    EvidenceRecord,
    Question,
    RetrievalRequest,
    RetrievalResult,
    SearchPlan,
    StrictModel,
)
from a5.ports.a2_mcp_client import A2MCPClient
from a5.runtime_config import IntegrationsConfig, load_runtime_config


class A2EvidencePayload(StrictModel):
    """Deprecated compatibility mirror of A2 v1.

    New A2→A3 composition must use ``a2.adapters.A2ToA3Normalizer``. This
    narrow mirror remains only at the A5 MCP boundary until that normalized
    Evidence is supplied directly.
    """

    schema_version: Literal["a2-evidence-v1"] = "a2-evidence-v1"
    id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    abstract_or_chunk: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    published_at: str | date | datetime | None = None
    url: str | None = None
    pmid: str | None = None
    doi: str | None = None
    nct_id: str | None = None
    guideline_name: str | None = None
    page: str | int | None = None
    evidence_level: str | None = None
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    fetched_at: str | datetime
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    mock: bool = False


class A2EvidenceAdapter:
    def __init__(
        self,
        config: IntegrationsConfig | None = None,
        *,
        allow_mock: bool = False,
    ) -> None:
        self._config = config or load_runtime_config().integrations
        self._allow_mock = allow_mock

    def adapt(self, payload: object) -> EvidenceRecord:
        item = payload if isinstance(payload, A2EvidencePayload) else A2EvidencePayload.model_validate(to_mapping(payload))
        is_mock = item.mock or bool(item.source_metadata.get("mock", False))
        looks_mock = fixture_like(item.id, item.title)
        if looks_mock and not is_mock:
            raise UpstreamContractError("fixture-like A2 Evidence must explicitly set mock=true")
        if is_mock:
            if not self._allow_mock:
                raise UpstreamContractError("mock A2 Evidence is disabled for this adapter")
            if any((item.pmid, item.doi, item.nct_id, item.url, item.guideline_name)):
                raise UpstreamContractError("mock A2 Evidence must not carry PMID/DOI/NCT/URL")
        else:
            missing = [name for name in self._config.a2_gate1_required_fields if not getattr(item, name, None)]
            if missing:
                raise UpstreamContractError("Gate1 missing required A2 fields: " + ", ".join(missing))
            if not any((item.pmid, item.doi, item.nct_id, item.guideline_name)):
                raise UpstreamContractError("Gate1 missing stable source identifier")
        published_at = parse_datetime(item.published_at)
        if item.published_at is not None and published_at is None:
            raise UpstreamContractError("A2 published_at is not an ISO date/datetime")
        metadata = {
            "adapter": "A2EvidenceAdapter",
            "contract_version": self._config.a2.contract_version,
            "authors": list(item.authors),
            "url": item.url,
            "pmid": item.pmid,
            "doi": item.doi,
            "nct_id": item.nct_id,
            "guideline_name": item.guideline_name,
            "page": item.page,
            "fetched_at": str(item.fetched_at) if item.fetched_at is not None else None,
            "content_hash": item.content_hash,
            "stable_id": item.id,
            "a2_source_metadata": dict(item.source_metadata),
            "source_integrity": "mock_fixture" if is_mock else "a2_mcp_normalized",
        }
        return EvidenceRecord(
            id=item.id,
            content=item.abstract_or_chunk,
            source_type=item.source_type,
            title=item.title,
            source_metadata=metadata,
            population=item.population,
            intervention=item.intervention,
            comparator=item.comparator,
            outcome=item.outcome,
            published_at=published_at,
            evidence_level=item.evidence_level,
            mock=is_mock,
        )


class A2ToA3EvidenceAdapter:
    """Deprecated shim; prefer ``a2.adapters.A2ToA3Normalizer``.

    A3 remains the owner of hashing, chunking, spans and index manifests. The
    A2 content hash is preserved in ``provenance`` instead of being presented
    as an A3-computed hash.
    """

    def adapt(self, payload: object) -> dict[str, Any]:
        item = (
            payload
            if isinstance(payload, A2EvidencePayload)
            else A2EvidencePayload.model_validate(to_mapping(payload))
        )
        is_mock = item.mock or bool(item.source_metadata.get("mock", False))
        if is_mock and any((item.pmid, item.doi, item.nct_id, item.url, item.guideline_name)):
            raise UpstreamContractError("mock A2 Evidence must not carry external identifiers")
        return {
            "id": item.id,
            "source_type": item.source_type,
            "title": item.title,
            "abstract_or_chunk": item.abstract_or_chunk,
            "authors": list(item.authors),
            "published_at": item.published_at,
            "url": item.url,
            "pmid": item.pmid,
            "doi": item.doi,
            "nct_id": item.nct_id,
            "guideline_name": item.guideline_name,
            "upstream_id": item.id,
            "page": str(item.page) if item.page is not None else None,
            "section": item.source_metadata.get("section"),
            "evidence_level": item.evidence_level,
            "population": item.population,
            "intervention": item.intervention,
            "comparator": item.comparator,
            "outcome": item.outcome,
            "fetched_at": item.fetched_at,
            "provenance": {
                "a2_schema_version": item.schema_version,
                "a2_content_hash": item.content_hash,
                "a2_source_metadata": dict(item.source_metadata),
            },
            "mock": is_mock,
            "tombstone": False,
        }


ToolArgumentBuilder = Callable[[Question, SearchPlan, RetrievalRequest], Mapping[str, Any]]


def provisional_tool_arguments(
    question: Question, plan: SearchPlan, request: RetrievalRequest
) -> Mapping[str, Any]:
    """Reviewed A2 search-tool request shape (queries + bounded limit)."""
    return {
        "queries": list(plan.queries),
        "limit": load_runtime_config().integrations.a2_search_limit,
    }


class A2MCPRetriever:
    """Normalize a bounded read-only MCP call without implementing A2's server."""

    def __init__(
        self,
        client: A2MCPClient,
        *,
        evidence_adapter: A2EvidenceAdapter | None = None,
        argument_builder: ToolArgumentBuilder | None = None,
        config: IntegrationsConfig | None = None,
    ) -> None:
        self._client = client
        self._config = config or load_runtime_config().integrations
        self._evidence_adapter = evidence_adapter or A2EvidenceAdapter(self._config)
        self._argument_builder = argument_builder or self._build_arguments

    def _build_arguments(
        self, question: Question, plan: SearchPlan, request: RetrievalRequest
    ) -> Mapping[str, Any]:
        del question, request
        return {"queries": list(plan.queries), "limit": self._config.a2_search_limit}

    def retrieve(
        self,
        question: Question,
        plan: SearchPlan,
        request: RetrievalRequest,
    ) -> RetrievalResult:
        tool_name = self._config.a2_tool_names.get(request.source_type)
        if tool_name is None:
            raise UpstreamRetrievalError(f"no provisional A2 tool route for {request.source_type}")
        raw = self._client.call_tool(tool_name, self._argument_builder(question, plan, request))
        envelope = to_mapping(raw)
        ok = envelope.get(self._config.a2_response_ok_field)
        if not isinstance(ok, bool):
            raise UpstreamRetrievalError("A2 MCP response is missing boolean ok status")
        if not ok:
            error = envelope.get("error")
            code = read_error_code(error)
            raise UpstreamRetrievalError(f"A2 MCP retrieval failed: {code}")
        raw_items = envelope.get(self._config.a2_response_items_field, [])
        if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, list):
            raise UpstreamContractError("A2 MCP evidence field must be a list")
        evidence: list[EvidenceRecord] = []
        quarantined: list[str] = []
        for index, item in enumerate(raw_items):
            try:
                evidence.append(self._evidence_adapter.adapt(item))
            except (UpstreamContractError, ValueError):
                quarantined.append(f"item-{index}")
        return RetrievalResult(
            evidence=evidence,
            tool_name=tool_name,
            diagnostics={
                "adapter": type(self).__name__,
                "contract_version": self._config.a2.contract_version,
                "upstream_status": "empty" if not raw_items else "ok",
                "adapter_status": (
                    "partial" if quarantined and evidence else "empty" if not evidence else "ok"
                ),
                "upstream_diagnostics": envelope.get("diagnostics"),
                "quarantined_items": quarantined,
                "schema_status": "reviewed_a2_evidence_v1",
            },
        )


def read_error_code(error: object) -> str:
    if isinstance(error, Mapping):
        return str(error.get("code", "UNKNOWN"))
    return "UNKNOWN"
