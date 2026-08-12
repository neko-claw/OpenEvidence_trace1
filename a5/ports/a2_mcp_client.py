from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class A2MCPClient(Protocol):
    """Minimal synchronous client seam; the real MCP SDK remains owned by A2."""

    def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> object:
        """Call one allowlisted, read-only A2 tool and return its raw payload."""
        ...
