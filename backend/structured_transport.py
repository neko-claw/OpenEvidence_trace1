from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import httpx


class OllamaStructuredTransport:
    """JSON-Schema transport for a local Ollama server.

    The transport owns no medical policy. All responses are validated again by
    the existing Pydantic adapters and A5 gates.
    """

    def __init__(self, base_url: str, *, timeout_seconds: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def available(self, model: str | None = None) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=2.0)
            response.raise_for_status()
            if model is None:
                return True
            names = {str(item.get("name")) for item in response.json().get("models", [])}
            return model in names or any(name.startswith(f"{model}:") for name in names)
        except Exception:
            return False

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        response_schema: Mapping[str, Any],
        timeout_seconds: float | None = None,
    ) -> Mapping[str, Any]:
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": model,
                "messages": [dict(item) for item in messages],
                "stream": False,
                "format": dict(response_schema),
                "options": {"temperature": 0, "num_ctx": 16384},
            },
            timeout=timeout_seconds or self.timeout_seconds,
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content")
        if not isinstance(content, str):
            raise ValueError("structured model returned no message content")
        payload = json.loads(content)
        if not isinstance(payload, Mapping):
            raise ValueError("structured model response must be an object")
        return payload
