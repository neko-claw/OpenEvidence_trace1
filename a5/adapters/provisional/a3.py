from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from a5.adapters.provisional.common import (
    UpstreamContractError,
    fixture_like,
    parse_datetime,
    read_field,
    to_mapping,
)
from a5.domain.models import EvidenceRecord, EvidenceSpan, StrictModel
from a5.runtime_config import IntegrationsConfig, load_runtime_config


class A3EvidencePayload(StrictModel):
    """Reviewed structural view of A3 Evidence at compatibility v0.3."""

    id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    abstract_or_chunk: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    published_at: str | date | datetime | None = None
    url: str | None = None
    pmid: str | None = None
    doi: str | None = None
    nct_id: str | None = None
    guideline_name: str | None = None
    upstream_id: str | None = None
    page: str | None = None
    section: str | None = None
    evidence_level: str | None = None
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    fetched_at: str | datetime | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    mock: bool = False
    tombstone: bool = False


class A3ChunkPayload(StrictModel):
    chunk_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    evidence_content_hash: str = Field(min_length=1)
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    raw_page: str | None = None
    section: str | None = None
    offset_scope: Literal["document"] = "document"
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    token_count: int = Field(ge=0)
    content_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_offsets(self) -> "A3ChunkPayload":
        if self.char_end <= self.char_start or self.char_end - self.char_start != len(self.text):
            raise ValueError("A3 chunk offsets must locate the complete chunk text")
        return self


class A3SpanPayload(StrictModel):
    span_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    offset_scope: Literal["chunk"] = "chunk"
    document_char_start: int = Field(ge=0)
    document_char_end: int = Field(ge=0)
    page: int | None = Field(default=None, ge=1)
    raw_page: str | None = None
    section: str | None = None
    chunk_content_hash: str = Field(min_length=1)
    evidence_content_hash: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_offsets(self) -> "A3SpanPayload":
        chunk_length = self.char_end - self.char_start
        document_length = self.document_char_end - self.document_char_start
        if chunk_length != len(self.text) or document_length != len(self.text):
            raise ValueError("A3 span offsets must locate the complete span text")
        return self


class A3EvidenceAdapter:
    """Map real A3 Evidence/Chunk/Span objects without synthesizing spans."""

    def __init__(self, config: IntegrationsConfig | None = None) -> None:
        self._config = config or load_runtime_config().integrations

    def adapt(
        self,
        evidence: object,
        chunks: list[object] | tuple[object, ...] = (),
        spans: list[object] | tuple[object, ...] = (),
    ) -> EvidenceRecord:
        raw = to_mapping(evidence)
        evidence_hash = read_field(evidence, "content_hash") or raw.pop("content_hash", None)
        stable_id = read_field(evidence, "stable_id") or raw.pop("stable_id", None)
        item = A3EvidencePayload.model_validate(raw)
        if item.tombstone:
            raise UpstreamContractError("tombstoned_evidence")
        looks_mock = fixture_like(item.id, item.title)
        if looks_mock and not item.mock:
            raise UpstreamContractError("fixture-like A3 Evidence must explicitly set mock=true")
        if item.mock and any((item.pmid, item.doi, item.nct_id, item.url, item.guideline_name)):
            raise UpstreamContractError("mock A3 Evidence must not carry PMID/DOI/NCT/URL/guideline ID")
        published_at = parse_datetime(item.published_at)
        if item.published_at is not None and published_at is None:
            raise UpstreamContractError("A3 published_at is not an ISO date/datetime")

        chunk_items: dict[str, A3ChunkPayload] = {}
        for raw_chunk in chunks:
            chunk = A3ChunkPayload.model_validate(to_mapping(raw_chunk))
            if chunk.evidence_id != item.id:
                raise UpstreamContractError(f"stale_chunk: {chunk.chunk_id} belongs to another Evidence")
            if evidence_hash and chunk.evidence_content_hash != evidence_hash:
                raise UpstreamContractError(f"evidence_hash_mismatch: {chunk.chunk_id}")
            chunk_items[chunk.chunk_id] = chunk

        mapped_spans: list[EvidenceSpan] = []
        for raw_span in spans:
            span = A3SpanPayload.model_validate(to_mapping(raw_span))
            chunk = chunk_items.get(span.chunk_id)
            if span.evidence_id != item.id or chunk is None:
                raise UpstreamContractError(f"stale_span: {span.span_id}")
            if span.chunk_content_hash != chunk.content_hash:
                raise UpstreamContractError(f"stale_span: chunk hash mismatch for {span.span_id}")
            if evidence_hash and span.evidence_content_hash != evidence_hash:
                raise UpstreamContractError(f"evidence_hash_mismatch: {span.span_id}")
            mapped_spans.append(
                EvidenceSpan(
                    span_id=span.span_id,
                    chunk_id=span.chunk_id,
                    text=span.text,
                    page=span.page,
                    raw_page=span.raw_page,
                    section=span.section,
                    char_start=span.char_start,
                    char_end=span.char_end,
                    offset_scope=span.offset_scope,
                    document_char_start=span.document_char_start,
                    document_char_end=span.document_char_end,
                    span_content_hash=span.content_hash,
                    chunk_content_hash=span.chunk_content_hash,
                    evidence_content_hash=span.evidence_content_hash,
                )
            )

        provenance_complete = bool(stable_id and item.url and item.fetched_at and evidence_hash)
        return EvidenceRecord(
            id=item.id,
            content=item.abstract_or_chunk,
            source_type=item.source_type,
            title=item.title,
            source_metadata={
                "adapter": "A3EvidenceAdapter",
                "contract_version": self._config.a3.contract_version,
                "stable_id": stable_id,
                "url": item.url,
                "authors": list(item.authors),
                "fetched_at": str(item.fetched_at) if item.fetched_at is not None else None,
                "content_hash": evidence_hash,
                "provenance": dict(item.provenance),
                "tombstone": item.tombstone,
                "selected_chunk_ids": list(chunk_items),
                "selected_span_ids": [span.span_id for span in mapped_spans],
                "source_integrity": (
                    "mock_fixture"
                    if item.mock
                    else "a3_provenance_validated" if provenance_complete else "a3_provenance_incomplete"
                ),
            },
            population=item.population,
            intervention=item.intervention,
            comparator=item.comparator,
            outcome=item.outcome,
            published_at=published_at,
            evidence_level=item.evidence_level,
            spans=mapped_spans,
            mock=item.mock,
        )
