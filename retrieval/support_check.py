"""Rule-based claim-evidence alignment pre-check and conflict detection (4.2 step 6).

A4 performs this cheap, deterministic pre-check only; the full NLI verifier
and publication gate remain with A5 (Gate5).  The verdict vocabulary is
ALIGNED | BACKGROUND | MISMATCH | INSUFFICIENT | UNKNOWN — deliberately *not*
A5's ``VerificationStatus.SUPPORTED`` — and every hint records
``method=token_overlap_heuristic`` plus the threshold version.  Hints never
block a search result and never become a medical-support verdict; they surface
as structured ``alignment_hints`` rows and warning text, and the A5 adapter
places them into ``RetrievalResult.diagnostics`` only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .bm25 import tokenize
from .config import RetrievalConfig
from .models import EvidenceChunk, Query, RetrievalAlignmentHint

_SUPPORTED_OVERLAP = 0.4
_BACKGROUND_OVERLAP = 0.15
_STOPWORDS = frozenset(
    {"in", "is", "of", "the", "and", "for", "with", "on", "at", "to", "a", "an",
     "are", "was", "were", "than", "or", "as", "by", "that", "this", "vs", "versus"}
)
_CONFLICT_POPULATION_PAIRS = frozenset(
    {
        frozenset({"children", "older adults"}),
        frozenset({"children", "adults"}),
        frozenset({"pregnant", "older adults"}),
    }
)
_TIME_CONFLICT_YEARS = 10


def check_alignment(
    query: Query,
    claims: Sequence[str],
    selected: Sequence[EvidenceChunk],
    config: RetrievalConfig | None = None,
) -> tuple[RetrievalAlignmentHint, ...]:
    """Alignment verdict per atomic claim against the selected evidence.

    Thresholds come from ``config`` when supplied (production path always
    passes the frozen ``RetrievalConfig``); otherwise the module defaults are
    used and ``threshold_version`` records that fact.
    """
    if not isinstance(claims, (str, bytes)) and isinstance(claims, Sequence):
        normalized = tuple(claims)
    else:
        raise ValueError("claims must be a sequence of nonblank strings")
    if any(not isinstance(claim, str) or not claim.strip() for claim in normalized):
        raise ValueError("claims must contain only nonblank strings")

    if config is not None:
        aligned_overlap = config.alignment_overlap_aligned
        background_overlap = config.alignment_overlap_background
        threshold_version = config.alignment_threshold_version
    else:
        aligned_overlap = _SUPPORTED_OVERLAP
        background_overlap = _BACKGROUND_OVERLAP
        threshold_version = "module-defaults-v1"

    results: list[RetrievalAlignmentHint] = []
    for index, claim in enumerate(normalized):
        claim_tokens = _content_tokens(claim)
        best_overlap = 0.0
        aligning: list[str] = []
        conflict_reason: str | None = None
        for chunk in selected:
            chunk_tokens = _content_tokens(f"{chunk.title} {chunk.text}")
            overlap = (
                len(claim_tokens & chunk_tokens) / len(claim_tokens) if claim_tokens else 0.0
            )
            if overlap >= background_overlap:
                aligning.append(chunk.evidence_id)
            if overlap > best_overlap:
                best_overlap = overlap
            if overlap >= aligned_overlap and _population_conflict(query, chunk):
                conflict_reason = f"population mismatch with {chunk.evidence_id}"
        if conflict_reason is not None:
            decision = "MISMATCH"
        elif best_overlap >= aligned_overlap:
            decision = "ALIGNED"
        elif best_overlap >= background_overlap:
            decision = "BACKGROUND"
        elif claim_tokens:
            decision = "INSUFFICIENT"
        else:
            decision = "UNKNOWN"
        results.append(
            RetrievalAlignmentHint(
                claim_index=index,
                claim_text=claim,
                decision=decision,
                evidence_ids=tuple(dict.fromkeys(aligning)),
                reason=conflict_reason or f"max token overlap {best_overlap:.2f}",
                method="token_overlap_heuristic",
                threshold_version=threshold_version,
            )
        )
    return tuple(results)


def detect_conflicts(selected: Sequence[EvidenceChunk]) -> tuple[tuple[str, str, str], ...]:
    """Return (evidence_id_a, evidence_id_b, reason) pairs for obvious conflicts."""
    if not isinstance(selected, Sequence):
        raise ValueError("selected must be a sequence of EvidenceChunk")
    conflicts: list[tuple[str, str, str]] = []
    for index, left in enumerate(selected):
        for right in selected[index + 1 :]:
            reason = _conflict_reason(left, right)
            if reason is not None:
                conflicts.append((left.evidence_id, right.evidence_id, reason))
    return tuple(conflicts)


def _conflict_reason(left: EvidenceChunk, right: EvidenceChunk) -> str | None:
    left_population = {term.casefold().strip() for term in left.pico_population}
    right_population = {term.casefold().strip() for term in right.pico_population}
    if left_population and right_population:
        for pair in _CONFLICT_POPULATION_PAIRS:
            if pair <= left_population | right_population and pair & left_population and pair & right_population:
                return "population"
    left_year = _year(left.published_at)
    right_year = _year(right.published_at)
    if left_year is not None and right_year is not None:
        if left_year >= 2000 and right_year >= 2000 and abs(left_year - right_year) >= _TIME_CONFLICT_YEARS:
            return "time"
    return None


def _year(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value).year
    except ValueError:
        return None


def _content_tokens(text: str) -> set[str]:
    """Content tokens with common stopwords removed (overlap is not inflated)."""
    return {token for token in tokenize(text) if token not in _STOPWORDS}


def _population_conflict(query: Query, chunk: EvidenceChunk) -> bool:
    query_population = {term.casefold().strip() for term in query.pico_population}
    chunk_population = {term.casefold().strip() for term in chunk.pico_population}
    if not query_population or not chunk_population:
        return False
    for pair in _CONFLICT_POPULATION_PAIRS:
        if pair & query_population and pair & chunk_population:
            return True
    return False
