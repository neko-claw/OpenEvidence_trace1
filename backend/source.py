from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from a2.adapters import A2ToA3NormalizationError, A2ToA3Normalizer
from a3.domain.models import Evidence

from backend.config import BackendConfig, load_backend_config


class A2ToolClient(Protocol):
    """Narrow MCP client boundary used by the backend composition."""

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class A2EvidenceBatch:
    source_alias: str
    tool_name: str | None
    tool_call_index: int
    evidence: tuple[Evidence, ...]
    diagnostics: dict[str, Any]
    error_code: str | None = None


class A2EvidenceSource:
    """Call one approved A2 MCP tool and normalize its output to A3 Evidence.

    One ``acquire`` invocation performs at most one MCP tool call. Tool-budget
    accounting stays in A5; this class reports the exact call index and never
    retries invisibly.
    """

    def __init__(
        self,
        client: A2ToolClient,
        *,
        normalizer: A2ToA3Normalizer | None = None,
        config: BackendConfig | None = None,
    ) -> None:
        if not callable(getattr(client, "call_tool", None)):
            raise ValueError("client must implement call_tool")
        self._client = client
        self._normalizer = normalizer or A2ToA3Normalizer()
        self._config = config or load_backend_config()
        self.call_count = 0

    def acquire(
        self,
        *,
        queries: list[str],
        source_alias: str,
        tool_call_index: int,
    ) -> A2EvidenceBatch:
        alias = source_alias.strip().casefold()
        tool_name = self._config.a2_source_routes.get(alias)
        base = {
            "backend_config_version": self._config.config_version,
            "backend_config_hash": self._config.snapshot_hash(),
            "source_alias": alias,
            "tool_call_index": tool_call_index,
            "query_count": len(queries),
            "result_limit": self._config.a2_result_limit,
        }
        if tool_name is None:
            return A2EvidenceBatch(
                source_alias=alias,
                tool_name=None,
                tool_call_index=tool_call_index,
                evidence=(),
                diagnostics={**base, "tool_called": False},
                error_code="UNSUPPORTED_SOURCE_ALIAS",
            )

        self.call_count += 1
        try:
            envelope = self._client.call_tool(
                tool_name,
                {"queries": list(queries), "limit": self._config.a2_result_limit},
            )
            normalized = self._normalizer.normalize_tool_response(envelope)
            evidence = tuple(Evidence.model_validate(item) for item in normalized)
        except A2ToA3NormalizationError as exc:
            return A2EvidenceBatch(
                source_alias=alias,
                tool_name=tool_name,
                tool_call_index=tool_call_index,
                evidence=(),
                diagnostics={**base, "tool_called": True, "safe_error": str(exc)},
                error_code="A2_CONTRACT_ERROR",
            )
        except Exception as exc:
            return A2EvidenceBatch(
                source_alias=alias,
                tool_name=tool_name,
                tool_call_index=tool_call_index,
                evidence=(),
                diagnostics={
                    **base,
                    "tool_called": True,
                    "safe_error": f"{type(exc).__name__}: A2 MCP call unavailable",
                },
                error_code="A2_MCP_ERROR",
            )

        return A2EvidenceBatch(
            source_alias=alias,
            tool_name=tool_name,
            tool_call_index=tool_call_index,
            evidence=evidence,
            diagnostics={
                **base,
                "tool_called": True,
                "result_count": len(evidence),
                "a2_diagnostics": dict(envelope.get("diagnostics") or {}),
            },
        )
