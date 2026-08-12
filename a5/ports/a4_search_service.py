from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class A4SearchService(Protocol):
    """Structural port for A4's independent ``search(query)`` contract."""

    def search(self, query: object) -> object:
        """Return an A4 SearchResult-like payload."""
        ...
