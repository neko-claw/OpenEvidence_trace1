from __future__ import annotations

from a2.models.evidence import A2Evidence
from a2.storage.dedup import canonical_key
from a5.domain.models import EvidenceRecord


def to_a5_evidence(record: A2Evidence) -> EvidenceRecord:
    """Map formal A2 evidence to A5's narrow compatibility view."""
    metadata = {
        "stable_id": record.id,
        "source_integrity": "mock_fixture" if record.mock else "a2_mcp_normalized",
        "a2_schema_version": record.schema_version,
        "url": record.url,
        "authors": list(record.authors),
        "pmid": record.pmid,
        "doi": record.doi,
        "nct_id": record.nct_id,
        "guideline_name": record.guideline_name,
        "page": record.page,
        "fetched_at": record.fetched_at.isoformat(),
        "content_hash": record.content_hash,
        "canonical_key": canonical_key(record),
        "aliases": list(record.source_metadata.get("aliases", [])),
        "source_metadata": dict(record.source_metadata),
        "mock": record.mock,
    }
    return EvidenceRecord(
        id=record.id,
        content=record.abstract_or_chunk,
        source_type=record.source_type.value,
        title=record.title,
        source_metadata=metadata,
        population=record.population,
        intervention=record.intervention,
        comparator=record.comparator,
        outcome=record.outcome,
        published_at=record.published_at,
        retrieval_score=None,
        evidence_level=record.evidence_level,
        spans=[],
        conflicts_with_ids=[],
        mock=record.mock,
    )
