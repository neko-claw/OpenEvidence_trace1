from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class A2ErrorCode(StrEnum):
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    UPSTREAM_HTTP_ERROR = "UPSTREAM_HTTP_ERROR"
    UPSTREAM_PARSE_ERROR = "UPSTREAM_PARSE_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"
    CACHE_ERROR = "CACHE_ERROR"
    MCP_ERROR = "MCP_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class A2Error(BaseModel):
    """Safe structured error returned across the MCP boundary."""

    model_config = ConfigDict(extra="forbid")
    code: A2ErrorCode
    source: str | None = None
    message: str
    retryable: bool = False
    http_status: int | None = None
    details: dict[str, Any] | None = None


class A2Exception(Exception):
    """Exception carrying an already-sanitized A2 error."""

    def __init__(self, error: A2Error) -> None:
        super().__init__(error.message)
        self.error = error
