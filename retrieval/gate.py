"""Gate1 source-provenance gate for evidence chunks (5.7 来源门禁).

The gate checks that a chunk carries everything a citation audit can rely on:
a stable identifier, a source type, a publication date *or* a versioned
guideline name, a URL, a fetch timestamp, and a content hash.  It does not
score medical quality — it only certifies that the record is *citable*.

The gate is intentionally strict and transparent: a verdict lists exactly
which contract fields are missing, so ingestion pipelines (``EvidenceStore``)
and data-quality reports can act on the same machine-readable result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .models import EvidenceChunk

# Source types that normally carry a publication date; the gate treats a
# versioned ``guideline_name`` as an acceptable date substitute for guidance.
_GUIDELINE_SOURCE_TYPES = frozenset({"guideline", "guidelines"})

_GATE_FIELDS = (
    "stable_id",
    "source_type",
    "published_at",
    "url",
    "fetched_at",
    "content_hash",
)


@dataclass(frozen=True, slots=True)
class SourceGateVerdict:
    """One chunk's Gate1 verdict: passed or an explicit list of missing fields."""

    passed: bool
    missing: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.passed, bool):
            raise ValueError("passed must be a bool")
        missing = tuple(dict.fromkeys(self.missing))
        if any(not isinstance(field, str) or not field.strip() for field in missing):
            raise ValueError("missing must contain only nonblank field names")
        object.__setattr__(self, "missing", missing)
        if self.passed and self.missing:
            raise ValueError("a passing verdict must not list missing fields")


def check_source_gate(chunk: EvidenceChunk) -> SourceGateVerdict:
    """Return whether ``chunk`` satisfies the Gate1 source-provenance gate.

    Required, in the vocabulary of 5.7: 稳定 ID、来源类型、发布时间/版本、
    URL、抓取时间、内容 hash.  Guidelines may substitute a versioned
    ``guideline_name`` for ``published_at``; other source types must carry a
    parseable ISO date in ``published_at``.
    """
    if not isinstance(chunk, EvidenceChunk):
        raise ValueError("chunk must be an EvidenceChunk")

    missing: list[str] = []
    if not isinstance(chunk.stable_id, str) or not chunk.stable_id.strip():
        missing.append("stable_id")
    if not isinstance(chunk.source_type, str) or not chunk.source_type.strip():
        missing.append("source_type")
    if not isinstance(chunk.url, str) or not chunk.url.strip():
        missing.append("url")
    if not isinstance(chunk.fetched_at, str) or not _parse_timestamp(chunk.fetched_at):
        missing.append("fetched_at")
    if not isinstance(chunk.content_hash, str) or not chunk.content_hash.strip():
        missing.append("content_hash")
    if not _has_publication_marker(chunk):
        missing.append("published_at")

    passed = not missing
    return SourceGateVerdict(passed=passed, missing=tuple(missing))


def _has_publication_marker(chunk: EvidenceChunk) -> bool:
    """Publication date, or a versioned guideline name for guidance sources."""
    if isinstance(chunk.published_at, str) and _parse_timestamp(chunk.published_at):
        return True
    is_guideline = chunk.source_type.strip().casefold() in _GUIDELINE_SOURCE_TYPES
    return is_guideline and bool(chunk.guideline_name.strip())


def _parse_timestamp(value: str) -> bool:
    """Accept an ISO date or a full ISO datetime; reject anything else."""
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.strip()
    try:
        date.fromisoformat(candidate)
        return True
    except ValueError:
        pass
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False
