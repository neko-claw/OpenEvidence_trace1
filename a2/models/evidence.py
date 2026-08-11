from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


A2_EVIDENCE_SCHEMA_VERSION = "a2-evidence-v1"


class SourceType(StrEnum):
    PUBMED = "pubmed"
    EUROPE_PMC = "europe_pmc"
    CLINICAL_TRIALS = "clinical_trials"
    GUIDELINE = "guideline"


class A2Evidence(BaseModel):
    """Frozen A2 source-normalized evidence contract."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = A2_EVIDENCE_SCHEMA_VERSION
    id: str = Field(min_length=1)
    source_type: SourceType
    title: str = Field(min_length=1)
    abstract_or_chunk: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    url: str | None = None
    pmid: str | None = None
    doi: str | None = None
    nct_id: str | None = None
    guideline_name: str | None = None
    page: int | None = Field(default=None, ge=1)
    evidence_level: str | None = None
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def frozen_schema(cls, value: str) -> str:
        if value != A2_EVIDENCE_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version: {value}")
        return value

    @field_validator("id", "title", "abstract_or_chunk")
    @classmethod
    def strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("required text must not be blank")
        return normalized

    @field_validator("pmid")
    @classmethod
    def normalize_pmid(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @field_validator("nct_id")
    @classmethod
    def normalize_nct(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("published_at", "fetched_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
