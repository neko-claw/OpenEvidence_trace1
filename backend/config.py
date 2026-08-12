from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "backend.yaml"


class BackendConfig(BaseModel):
    """Versioned composition settings; not a medical policy asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    config_version: str = Field(min_length=1)
    backend_version: str = Field(min_length=1)
    a2_result_limit: int = Field(ge=1, le=50)
    a2_source_routes: dict[str, str] = Field(min_length=1)
    chunk_policy_version: str = Field(min_length=1)
    chunk_max_chars: int = Field(ge=200)
    chunk_overlap_chars: int = Field(ge=0)
    chunk_natural_boundary_ratio: float = Field(gt=0.0, le=1.0)
    default_retrieval_condition: str = Field(pattern=r"^R[0-3]$")

    @field_validator("a2_source_routes")
    @classmethod
    def validate_routes(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {
            "search_pubmed",
            "search_europe_pmc",
            "search_trials",
            "search_guidelines",
        }
        normalized = {key.strip().casefold(): tool.strip() for key, tool in value.items()}
        if any(not key or tool not in allowed for key, tool in normalized.items()):
            raise ValueError("A2 source routes must use nonblank aliases and approved read-only search tools")
        return normalized

    def snapshot(self) -> dict[str, object]:
        return self.model_dump(mode="json")

    def snapshot_hash(self) -> str:
        canonical = json.dumps(
            self.snapshot(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return sha256(canonical.encode("utf-8")).hexdigest()


def load_backend_config(path: str | Path = DEFAULT_CONFIG_PATH) -> BackendConfig:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return BackendConfig.model_validate(payload)
