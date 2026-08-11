from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server import MCPServer

from a2.models.errors import A2Error, A2ErrorCode, A2Exception


class A2MCPClient:
    """Official MCP v2 client supporting in-process tests and local stdio."""

    def __init__(self, server: MCPServer | None = None, stdio_parameters: StdioServerParameters | None = None) -> None:
        if server is None and stdio_parameters is None:
            raise ValueError("server or stdio_parameters is required")
        self.server = server
        self.stdio_parameters = stdio_parameters

    @classmethod
    def local_stdio(cls, root: Path | None = None) -> "A2MCPClient":
        """Create a client that launches a fresh local stdio server."""
        repo = root or Path(__file__).parents[2]
        return cls(stdio_parameters=StdioServerParameters(command=sys.executable, args=["-m", "a2.mcp.server"], cwd=repo))

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Make one MCP tool invocation and return its structured envelope."""
        return asyncio.run(self._call_tool(name, arguments))

    def list_tools(self) -> list[dict[str, Any]]:
        """Discover tools through the official MCP client abstraction."""
        return asyncio.run(self._list_tools())

    def _target(self) -> Any:
        return self.server if self.server is not None else stdio_client(self.stdio_parameters)

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            async with Client(self._target(), raise_exceptions=True) as client:
                result = await client.call_tool(name, arguments)
        except Exception as exc:
            raise A2Exception(A2Error(code=A2ErrorCode.MCP_ERROR, source=None, message=f"MCP tool call failed: {type(exc).__name__}", retryable=False)) from exc
        payload = result.structured_content
        if payload is None and result.content:
            text = getattr(result.content[0], "text", None)
            if text:
                payload = json.loads(text)
        if not isinstance(payload, dict):
            raise A2Exception(A2Error(code=A2ErrorCode.MCP_ERROR, source=None, message="MCP tool returned no structured object"))
        return payload

    async def _list_tools(self) -> list[dict[str, Any]]:
        async with Client(self._target(), raise_exceptions=True) as client:
            result = await client.list_tools()
        return [tool.model_dump(mode="json") for tool in result.tools]
