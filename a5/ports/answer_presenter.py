from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VerifiedClaimPresenter(Protocol):
    """Optional post-Gate5 language presentation boundary.

    The source statement remains the authoritative, verified Claim. Returning
    ``None`` means that no safe localized presentation could be produced.
    """

    def present(self, statement: str) -> str | None: ...
