from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OpenAICompatibleStructuredTransport(Protocol):
    """Injected JSON-schema transport; SDK, endpoint and credentials stay outside A5."""

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...
