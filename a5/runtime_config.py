from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field

from a5.domain.enums import RetrievalScoreKind, RetrievalScoreScope, UncertaintyLevel
from a5.domain.models import RuntimeConfigSnapshot, StrictModel


class AgentConfig(StrictModel):
    config_version: str
    agent_version: str
    state_machine_version: str
    max_tool_calls: int = Field(ge=1, le=20)


class Gate2Config(StrictModel):
    min_candidates: int = Field(ge=1)
    min_top_score: float = Field(ge=0.0, le=1.0)
    min_source_types: int = Field(ge=1)
    min_source_diversity: float = Field(ge=0.0, le=1.0)
    accepted_evidence_levels: list[str]
    max_age_days: int = Field(ge=1)
    min_fresh_fraction: float = Field(ge=0.0, le=1.0)
    max_conflicts: int = Field(ge=0)
    required_score_kind: RetrievalScoreKind
    required_score_scope: RetrievalScoreScope
    require_calibrated_score: bool


class Gate1Config(StrictModel):
    required_source_metadata: list[str]
    accepted_integrity_markers: list[str]


class Gate5Config(StrictModel):
    require_span: bool
    require_pico_when_claim_specified: bool
    require_time_when_fresh: bool
    supported_entailment_threshold: float = Field(ge=0.0, le=1.0)
    require_numeric_consistency: bool


class Gate6Config(StrictModel):
    critical_allowed_uncertainty: list[UncertaintyLevel]


class GatesConfig(StrictModel):
    config_version: str
    threshold_status: str
    gate0_version: str
    gate1_version: str
    gate2_version: str
    gate5_version: str
    gate6_version: str
    gate1: Gate1Config
    gate2: Gate2Config
    gate5: Gate5Config
    gate6: Gate6Config


class SkillSelection(StrictModel):
    version: str
    prompt_version: str
    manifest: str


class ClassifierConfig(StrictModel):
    policy_version: str
    fallback_type: str
    keyword_types: dict[str, list[str]]
    rules: dict[str, dict[str, Any]]


class SkillsConfig(StrictModel):
    config_version: str
    evidence_research: SkillSelection
    citation_audit: SkillSelection
    prompt_versions: dict[str, str]
    classifier: ClassifierConfig


class ModelsConfig(StrictModel):
    config_version: str
    claim_generator: str
    claim_verifier: str
    textual_support_evaluator: str


class UpstreamContractRef(StrictModel):
    contract_version: str
    source_ref: str
    status: str


class ExperimentalCapabilityConfig(StrictModel):
    owner: str
    enabled: bool
    status: str
    model: str | None = None
    required_dev_metrics: list[str] = Field(default_factory=list)


class IntegrationsConfig(StrictModel):
    config_version: str
    status: str
    a1: UpstreamContractRef
    a2: UpstreamContractRef
    a3: UpstreamContractRef
    a4: UpstreamContractRef
    embedding_capability: ExperimentalCapabilityConfig
    cross_encoder_capability: ExperimentalCapabilityConfig
    a2_tool_names: dict[str, str]
    a2_search_limit: int = Field(ge=1, le=50)
    a2_gate1_required_fields: list[str]
    a2_response_ok_field: str
    a2_response_items_field: str
    a4_question_type_map: dict[str, str]
    a4_freshness_map: dict[str, str]
    a4_source_type_map: dict[str, str]
    a4_topic_map: dict[str, str]


class RuntimeConfig(StrictModel):
    agent: AgentConfig
    gates: GatesConfig
    skills: SkillsConfig
    models: ModelsConfig
    integrations: IntegrationsConfig

    def snapshot(self) -> RuntimeConfigSnapshot:
        return RuntimeConfigSnapshot(
            agent=self.agent.model_dump(mode="json"),
            gates=self.gates.model_dump(mode="json"),
            skills=self.skills.model_dump(mode="json"),
            models=self.models.model_dump(mode="json"),
            integrations=self.integrations.model_dump(mode="json"),
        )


def _load_json_yaml(path: Path) -> dict[str, Any]:
    """Load JSON-compatible YAML without adding a production dependency.

    JSON is a strict YAML subset. Assets deliberately use JSON syntax while
    retaining ``.yaml`` so A1/A2 integrations may switch to a YAML parser later.
    """

    return json.loads(path.read_text(encoding="utf-8"))


def load_runtime_config(config_dir: Path | None = None) -> RuntimeConfig:
    root = Path(__file__).parents[1]
    directory = config_dir or root / "config"
    return RuntimeConfig(
        agent=AgentConfig.model_validate(_load_json_yaml(directory / "agent.yaml")),
        gates=GatesConfig.model_validate(_load_json_yaml(directory / "gates.yaml")),
        skills=SkillsConfig.model_validate(_load_json_yaml(directory / "skills.yaml")),
        models=ModelsConfig.model_validate(_load_json_yaml(directory / "models.yaml")),
        integrations=IntegrationsConfig.model_validate(
            _load_json_yaml(directory / "integrations.yaml")
        ),
    )
