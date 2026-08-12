from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


ROOT = Path(__file__).parents[1]


class HTTPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connect_timeout_seconds: float = Field(gt=0)
    read_timeout_seconds: float = Field(gt=0)
    total_timeout_seconds: float = Field(gt=0)
    retry_count: int = Field(ge=0, le=10)
    backoff_seconds: float = Field(ge=0)
    user_agent: str


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cache_directory: Path
    sqlite_path: Path


class A2Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    evidence_schema_version: str
    mcp_sdk_version: str
    mcp_protocol_version: str
    http: HTTPConfig
    storage: StorageConfig
    default_result_limit: int = Field(ge=1)
    max_result_limit: int = Field(ge=1)
    max_queries: int = Field(ge=1)
    max_query_length: int = Field(ge=1)
    sources: dict[str, dict[str, Any]]


def load_a2_config(path: Path | None = None) -> A2Config:
    """Load and strictly validate the versioned A2 configuration."""
    source = path or ROOT / "config" / "a2.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    storage = data["storage"]
    for key in ("cache_directory", "sqlite_path"):
        candidate = Path(storage[key])
        storage[key] = candidate if candidate.is_absolute() else ROOT / candidate
    guidelines = data["sources"]["guidelines"]
    manifest = Path(guidelines["manifest_path"])
    guidelines["manifest_path"] = str(manifest if manifest.is_absolute() else ROOT / manifest)
    return A2Config.model_validate(data)
