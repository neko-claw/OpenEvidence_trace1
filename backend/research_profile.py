from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESEARCH_PROFILE = ROOT / "config" / "research_profile.json"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResearchScopeConfig(StrictModel):
    topics: list[str] = Field(min_length=1)
    notice: str = Field(min_length=1)


class ResearchRetrievalConfig(StrictModel):
    condition: str = Field(pattern=r"^R[0-3]$")
    min_candidates: int = Field(ge=1)
    min_top_ranking_score: float = Field(ge=0.0, le=1.0)
    min_source_types: int = Field(ge=1)
    min_source_diversity: float = Field(ge=0.0, le=1.0)
    accepted_evidence_levels: list[str] = Field(min_length=1)
    max_age_days: int = Field(ge=1)
    min_fresh_fraction: float = Field(ge=0.0, le=1.0)
    max_conflicts: int = Field(ge=0)


class ResearchModelConfig(StrictModel):
    ollama_base_url: str = Field(min_length=1)
    generation_model: str = Field(min_length=1)
    verification_model: str = Field(min_length=1)
    request_timeout_seconds: float = Field(gt=0.0, le=600.0)
    enable_local_answer_presentation: bool = False
    answer_presentation_model: str = "Qwen2.5-1.5B-Instruct"
    answer_presentation_model_path: str = ".local/models/Qwen2.5-1.5B-Instruct"


class ResearchGenerationConfig(StrictModel):
    max_claims: int = Field(ge=1, le=12)
    min_span_chars: int = Field(ge=10)
    max_span_chars: int = Field(ge=50)


class ResearchProfile(StrictModel):
    profile_version: str = Field(min_length=1)
    scope: ResearchScopeConfig
    retrieval: ResearchRetrievalConfig
    models: ResearchModelConfig
    generation: ResearchGenerationConfig


def load_research_profile(path: str | Path = DEFAULT_RESEARCH_PROFILE) -> ResearchProfile:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ResearchProfile.model_validate(payload)
