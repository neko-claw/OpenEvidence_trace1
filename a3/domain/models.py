from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EVIDENCE_SCHEMA_VERSION = "a3-evidence-v0.2"
CHUNK_SCHEMA_VERSION = "a3-chunk-v0.2"
SPAN_SCHEMA_VERSION = "a3-span-v0.2"
A3_CONTRACT_VERSION = "a3-compat-v0.3"
SEARCH_HIT_SCHEMA_VERSION = "a3-search-hit-v0.3"
INDEX_MANIFEST_SCHEMA_VERSION = "a3-index-manifest-v0.3"


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PICO(StrictModel):
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None

    @field_validator("population", "intervention", "comparator", "outcome")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class Evidence(StrictModel):
    id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    abstract_or_chunk: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
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
    fetched_at: datetime | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    mock: bool = False
    tombstone: bool = False

    @model_validator(mode="after")
    def guard_mock_identifiers(self) -> "Evidence":
        if self.mock and any((self.url, self.pmid, self.doi, self.nct_id, self.guideline_name)):
            raise ValueError("mock evidence cannot carry real-world identifiers, URLs, or guideline IDs")
        return self

    @property
    def stable_id(self) -> str:
        if self.pmid:
            return f"pmid:{self.pmid.strip()}"
        if self.doi:
            return f"doi:{self.doi.strip().casefold()}"
        if self.nct_id:
            return f"nct:{self.nct_id.strip().upper()}"
        if self.guideline_name:
            locator = self.page or self.section or "unknown"
            return f"guideline:{self.guideline_name.strip().casefold()}:{locator.strip().casefold()}"
        return f"upstream:{(self.upstream_id or self.id).strip()}"

    @property
    def content_hash(self) -> str:
        return canonical_hash({
            "source_type": self.source_type.strip().casefold(), "stable_id": self.stable_id,
            "title": " ".join(self.title.split()), "text": " ".join(self.abstract_or_chunk.split()),
            "authors": [" ".join(x.split()) for x in self.authors],
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "url": self.url, "pmid": self.pmid, "doi": self.doi, "nct_id": self.nct_id,
            "guideline_name": self.guideline_name, "page": self.page, "section": self.section,
            "evidence_level": self.evidence_level, "population": self.population,
            "intervention": self.intervention, "comparator": self.comparator, "outcome": self.outcome,
            "mock": self.mock, "tombstone": self.tombstone,
        })


class Chunk(StrictModel):
    chunk_id: str
    evidence_id: str
    evidence_content_hash: str
    text: str
    page: int | None = Field(default=None, ge=1)
    raw_page: str | None = None
    section: str | None = None
    offset_scope: Literal["document"] = "document"
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    token_count: int = Field(ge=0)
    content_hash: str

    @model_validator(mode="after")
    def validate_offsets(self) -> "Chunk":
        if self.char_end <= self.char_start:
            raise ValueError("chunk char_end must be greater than char_start")
        if self.char_end - self.char_start != len(self.text):
            raise ValueError("chunk document offsets must match text length")
        return self


class EvidenceSpan(StrictModel):
    span_id: str
    evidence_id: str
    chunk_id: str
    text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    offset_scope: Literal["chunk"] = "chunk"
    document_char_start: int = Field(ge=0)
    document_char_end: int = Field(ge=0)
    page: int | None = Field(default=None, ge=1)
    raw_page: str | None = None
    section: str | None = None
    chunk_content_hash: str
    evidence_content_hash: str
    content_hash: str

    @model_validator(mode="after")
    def validate_offsets(self) -> "EvidenceSpan":
        if self.char_end <= self.char_start:
            raise ValueError("span char_end must be greater than char_start")
        if self.document_char_end <= self.document_char_start:
            raise ValueError("span document_char_end must be greater than document_char_start")
        if self.char_end - self.char_start != len(self.text):
            raise ValueError("span chunk offsets must match text length")
        if self.document_char_end - self.document_char_start != len(self.text):
            raise ValueError("span document offsets must match text length")
        return self


class SearchSpanRef(StrictModel):
    span_id: str
    chunk_id: str
    text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    offset_scope: Literal["chunk"] = "chunk"
    document_char_start: int = Field(ge=0)
    document_char_end: int = Field(ge=0)
    page: int | None = Field(default=None, ge=1)
    raw_page: str | None = None
    section: str | None = None
    span_content_hash: str
    chunk_content_hash: str
    evidence_content_hash: str


class SearchHit(StrictModel):
    document_kind: Literal["evidence", "wiki_navigation"] = "evidence"
    channel: Literal["lexical", "vector"]
    rank: int = Field(ge=1)
    raw_score: float | None = None
    distance: float | None = None
    chunk_id: str
    evidence_id: str | None
    title: str
    text: str
    source_type: str
    evidence_level: str | None = None
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    published_at: datetime | None = None
    page: int | None = Field(default=None, ge=1)
    raw_page: str | None = None
    section: str | None = None
    mock: bool
    tombstone: bool | None
    live_state: Literal["live", "tombstoned", "navigation_only", "UNKNOWN"]
    chunk_content_hash: str | None
    evidence_content_hash: str | None
    span_refs: list[SearchSpanRef]
    corpus_version: str
    index_version: str
    chunk_policy_version: str
    bm25_tokenizer_version: str
    embedding_provider: str
    embedding_model: str
    embedding_revision: str | None
    embedding_source_kind: str
    wiki_builder_version: str
    config_schema_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def navigation_is_not_evidence(self) -> "SearchHit":
        if self.document_kind == "wiki_navigation":
            if self.evidence_id is not None or not self.mock or self.tombstone is not None:
                raise ValueError("Wiki navigation cannot be represented as medical Evidence")
            if self.live_state != "navigation_only" or self.chunk_content_hash is not None \
                    or self.evidence_content_hash is not None or self.span_refs:
                raise ValueError("Wiki navigation must not carry Evidence/Chunk/Span provenance")
        return self


class IndexManifest(StrictModel):
    manifest_schema_version: str
    evidence_schema_version: str
    chunk_schema_version: str
    span_schema_version: str
    search_hit_schema_version: str
    config_schema_version: str
    corpus_version: str
    index_version: str
    chunk_policy_version: str
    chunk_policy: dict[str, Any]
    bm25_tokenizer_version: str
    embedding_provider: str
    embedding_model: str
    embedding_revision: str | None = None
    embedding_source_kind: str
    embedding_mode: str = "dense"
    vector_distance: str = "cosine"
    wiki_builder_version: str
    requested_config: dict[str, Any]
    runtime_effective_config: dict[str, Any]
    created_at: datetime = Field(default_factory=utc_now)
