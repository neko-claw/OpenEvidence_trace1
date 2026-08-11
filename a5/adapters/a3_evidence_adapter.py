from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from a3.domain.models import Chunk, Evidence, EvidenceSpan
from a5.domain.models import EvidenceRecord, EvidenceSpan as A5EvidenceSpan


def _page(value: int | str | None) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    if value and value.isdecimal() and int(value) > 0:
        return int(value)
    return None


def adapt_a3_evidence(evidence: Evidence, selected_chunks: Sequence[Chunk], spans: Sequence[EvidenceSpan],
                      *, index_version: str, corpus_version: str) -> EvidenceRecord:
    chunks = [c for c in selected_chunks if c.evidence_id == evidence.id]
    if not chunks:
        raise ValueError("A5 adapter requires at least one selected A3 chunk")
    chunk_ids = {c.chunk_id for c in chunks}
    selected_spans = [s for s in spans if s.evidence_id == evidence.id and s.chunk_id in chunk_ids]
    raw_pages = list(dict.fromkeys(c.raw_page for c in chunks if c.raw_page is not None))
    metadata: dict[str, Any] = {"stable_id": evidence.stable_id, "content_hash": evidence.content_hash,
        "raw_page": raw_pages[0] if len(raw_pages) == 1 else raw_pages, "chunk_ids": [c.chunk_id for c in chunks],
        "index_version": index_version, "corpus_version": corpus_version, "provenance": evidence.provenance}
    for key in ("url", "pmid", "doi", "nct_id", "guideline_name"):
        value = getattr(evidence, key)
        if value is not None:
            metadata[key] = value
    return EvidenceRecord(id=evidence.id, content="\n".join(c.text for c in chunks),
        source_type=evidence.source_type, title=evidence.title, source_metadata=metadata,
        population=evidence.population, intervention=evidence.intervention,
        comparator=evidence.comparator, outcome=evidence.outcome,
        published_at=evidence.published_at, retrieval_score=None, evidence_level=evidence.evidence_level,
        spans=[A5EvidenceSpan(span_id=s.span_id, text=s.text, chunk_id=s.chunk_id,
            page=_page(s.page), section=s.section) for s in selected_spans], mock=evidence.mock)
