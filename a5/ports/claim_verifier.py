from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from a5.domain.models import Claim, EvidenceRecord, VerificationContext, VerificationResult


@runtime_checkable
class ClaimVerifier(Protocol):
    def verify(
        self,
        claim: Claim,
        evidence: Sequence[EvidenceRecord],
        context: VerificationContext,
    ) -> VerificationResult:
        """Verify one atomic claim against only this run's evidence whitelist."""
        ...
