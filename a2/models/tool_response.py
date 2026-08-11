from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from a2.models.errors import A2Error
from a2.models.evidence import A2_EVIDENCE_SCHEMA_VERSION, A2Evidence


class ToolDiagnostics(BaseModel):
    model_config = ConfigDict(extra="allow")
    tool_name: str
    source: str | None = None
    cache_hit: bool | None = None
    result_count: int = 0
    upstream_request_count: int = 0
    retry_count: int = 0
    latency_ms: float = 0.0
    schema_version: str = A2_EVIDENCE_SCHEMA_VERSION
    upstream_api_version: str | None = None


class ToolResponse(BaseModel):
    """Uniform structured MCP tool envelope."""

    model_config = ConfigDict(extra="forbid")
    schema_version: str = A2_EVIDENCE_SCHEMA_VERSION
    ok: bool
    evidence: list[A2Evidence] = Field(default_factory=list)
    diagnostics: ToolDiagnostics
    error: A2Error | None = None
    result: dict[str, Any] | None = None
