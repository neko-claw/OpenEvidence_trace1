"""Evidence Mixer: blend the verified and discovery pools before reranking.

Sits between RRF fusion and feature reranking (4.3 / 可信池).  RRF candidates
are split by ``EvidenceChunk.trust_tier``; ``verified_ratio`` of the candidate
limit is taken from the verified pool (in RRF order) and the rest from the
discovery pool.  Both pools then compete in the *real* rerank: this is a
recall-pool shape, not a post-rerank quota cut.

A verified-pool shortfall is filled from discovery so an empty verified pool
degrades to pure discovery instead of an empty result; the shortfall is
recorded in ``MixLog`` for the audit trail.  Chunk-level dedup and per-source
caps stay with their existing owners (intake and MMR).

`ponytail:` promotion is deliberately not handled here — A2 resolves
PMID/DOI/NCT and rewrites ``trust_tier`` before retrieval; mixing only reads
the tier.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .models import Candidate


@dataclass(frozen=True, slots=True)
class MixLog:
    """Audit record of one evidence-mixing decision."""

    verified_ratio: float
    verified_target: int
    discovery_target: int
    verified_available: int
    discovery_available: int
    verified_taken: int
    discovery_taken: int
    shortfall: int

    @property
    def summary(self) -> str:
        return (
            f"mix verified/discovery={self.verified_taken}/{self.discovery_taken}"
            f" (ratio {self.verified_ratio:.2f}, target {self.verified_target}/{self.discovery_target},"
            f" shortfall {self.shortfall})"
        )


def mix_evidence(
    candidates: Sequence[Candidate],
    verified_ratio: float,
    candidate_limit: int,
) -> tuple[list[Candidate], MixLog]:
    """Take ``verified_ratio`` of the limit from the verified pool, rest from discovery.

    Returns ``(mixed, log)`` where ``mixed`` preserves each pool's RRF order
    (verified block first) and is capped at ``candidate_limit``.
    """
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise ValueError("candidates must be a sequence of Candidate")
    if (
        not isinstance(verified_ratio, (int, float))
        or isinstance(verified_ratio, bool)
        or not 0 <= verified_ratio <= 1
    ):
        raise ValueError("verified_ratio must be a finite number in [0, 1]")
    if not isinstance(candidate_limit, int) or isinstance(candidate_limit, bool) or candidate_limit <= 0:
        raise ValueError("candidate_limit must be a positive integer")
    if any(not isinstance(candidate, Candidate) for candidate in candidates):
        raise ValueError("candidates must contain only Candidate values")

    verified = [candidate for candidate in candidates if candidate.chunk.trust_tier == "verified"]
    discovery = [candidate for candidate in candidates if candidate.chunk.trust_tier == "discovery"]

    verified_target = round(candidate_limit * verified_ratio)
    discovery_target = candidate_limit - verified_target

    verified_taken = min(verified_target, len(verified))
    shortfall = verified_target - verified_taken
    discovery_taken = min(discovery_target + shortfall, len(discovery))

    mixed = verified[:verified_taken] + discovery[:discovery_taken]
    log = MixLog(
        verified_ratio=verified_ratio,
        verified_target=verified_target,
        discovery_target=discovery_target,
        verified_available=len(verified),
        discovery_available=len(discovery),
        verified_taken=verified_taken,
        discovery_taken=discovery_taken,
        shortfall=shortfall,
    )
    return mixed, log
