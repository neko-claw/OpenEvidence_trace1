from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator, model_validator

from a3.domain.models import StrictModel


class ChunkPolicyConfig(StrictModel):
    version: str = Field(min_length=1)
    max_chars: int = Field(gt=0)
    overlap_chars: int = Field(ge=0)
    natural_boundary_ratio: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def overlap_is_smaller_than_chunk(self) -> "ChunkPolicyConfig":
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")
        return self


class BM25Config(StrictModel):
    tokenizer_version: str = Field(min_length=1)
    root: Path


class EmbeddingConfig(StrictModel):
    provider: Literal["flagembedding"]
    model: str = Field(min_length=1)
    revision: str | None = None
    local_path_env: str = Field(min_length=1)
    mode: Literal["dense"]
    normalize: Literal[True]


class VectorConfig(StrictModel):
    root: Path
    distance: Literal["cosine"]


class WikiTopicConfig(StrictModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(min_length=1)
    synonyms: list[str] = Field(default_factory=list)
    mesh: list[str] = Field(default_factory=list)

    @field_validator("synonyms", "mesh")
    @classmethod
    def unique_nonblank_terms(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.split()) for value in values]
        if any(not value for value in normalized):
            raise ValueError("topic terms must not be blank")
        if len({value.casefold() for value in normalized}) != len(normalized):
            raise ValueError("topic terms must be unique")
        return normalized


class WikiConfig(StrictModel):
    root: Path
    builder_version: str = Field(min_length=1)
    generator: Literal["deterministic-offline"]
    topics: list[WikiTopicConfig] = Field(min_length=1)

    @field_validator("topics")
    @classmethod
    def unique_topics(cls, values: list[WikiTopicConfig]) -> list[WikiTopicConfig]:
        slugs = [value.slug for value in values]
        if len(slugs) != len(set(slugs)):
            raise ValueError("wiki topic slugs must be unique")
        return values


class A3Config(StrictModel):
    schema_version: str = Field(min_length=1)
    database: Path
    mock_fixture: Path
    corpus_cutoff: date | None = None
    chunk_policy: ChunkPolicyConfig
    bm25: BM25Config
    embedding: EmbeddingConfig
    vector: VectorConfig
    wiki: WikiConfig


@dataclass(frozen=True)
class LoadedA3Config:
    config: A3Config
    project_root: Path
    source: Path

    def resolve(self, value: Path) -> Path:
        return value if value.is_absolute() else self.project_root / value

    @property
    def database_path(self) -> Path:
        return self.resolve(self.config.database)

    @property
    def fixture_path(self) -> Path:
        return self.resolve(self.config.mock_fixture)

    @property
    def bm25_root(self) -> Path:
        return self.resolve(self.config.bm25.root)

    @property
    def vector_root(self) -> Path:
        return self.resolve(self.config.vector.root)

    @property
    def wiki_root(self) -> Path:
        return self.resolve(self.config.wiki.root)

    def requested_config(self) -> dict[str, object]:
        """Validated requested YAML values before runtime provider overrides."""
        return self.config.model_dump(mode="json")

    def runtime_effective_config(self, *, embedding_provider: str, embedding_model: str,
                                 embedding_revision: str | None, embedding_source_kind: str,
                                 fixture_path: str | Path | None = None) -> dict[str, object]:
        """Single portable snapshot of values that actually drive this build."""
        snapshot = self.config.model_dump(mode="json")
        embedding = dict(snapshot["embedding"])
        embedding.update(provider=embedding_provider, model=embedding_model,
                         revision=embedding_revision, source_kind=embedding_source_kind)
        snapshot["embedding"] = embedding
        if fixture_path is not None:
            snapshot["mock_fixture"] = str(fixture_path)
        return snapshot


class ConfigLoader:
    @staticmethod
    def load(path: str | Path, *, project_root: str | Path | None = None) -> LoadedA3Config:
        source = Path(path).resolve()
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("A3 configuration must be a YAML mapping")
        config = A3Config.model_validate(raw)
        root = Path(project_root).resolve() if project_root is not None else source.parent.parent
        return LoadedA3Config(config=config, project_root=root, source=source)
