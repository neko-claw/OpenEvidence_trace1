from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    page: str | None = None
    section: str | None = None
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    token_count: int = Field(ge=0)
    content_hash: str


class EvidenceSpan(StrictModel):
    span_id: str
    evidence_id: str
    chunk_id: str
    text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    page: str | None = None
    section: str | None = None
    content_hash: str


class SearchHit(StrictModel):
    channel: Literal["lexical", "vector"]
    rank: int = Field(ge=1)
    raw_score: float | None = None
    distance: float | None = None
    chunk_id: str
    evidence_id: str
    title: str
    text: str
    source_type: str
    evidence_level: str | None = None
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    published_at: datetime | None = None
    page: str | None = None
    section: str | None = None
    index_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexManifest(StrictModel):
    corpus_version: str
    index_version: str
    chunk_policy_version: str
    chunk_policy: dict[str, Any]
    bm25_tokenizer_version: str
    embedding_provider: str
    embedding_model: str
    embedding_revision: str | None = None
    embedding_mode: str = "dense"
    vector_distance: str = "cosine"
    wiki_builder_version: str
    created_at: datetime = Field(default_factory=utc_now)
