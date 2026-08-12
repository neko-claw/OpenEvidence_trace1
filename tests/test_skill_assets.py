import json
from pathlib import Path

from a5.domain.models import (
    CitationAuditInput,
    CitationAuditOutput,
    EvidenceResearchInput,
    EvidenceResearchOutput,
)
from a5.runtime_config import load_runtime_config
from a5.skills.loader import PromptLoader, SkillLoader


ROOT = Path(__file__).parents[1]


def _assert_schema_root_matches(model, schema: dict) -> None:
    generated = model.model_json_schema()
    assert schema == generated


def test_manifests_prompts_schemas_and_fixtures_load() -> None:
    config = load_runtime_config()
    loader = SkillLoader()
    for selection in (config.skills.evidence_research, config.skills.citation_audit):
        skill = loader.load(selection.manifest, expected_version=selection.version)
        assert skill.prompt_text
        assert skill.manifest.prompt_version == selection.prompt_version
        assert skill.input_schema["type"] == "object"
        assert skill.output_schema["type"] == "object"
        assert set(skill.fixture) == {"input", "output"}


def test_skill_loader_resolves_name_version_and_implementation() -> None:
    config = load_runtime_config()
    loaded = SkillLoader().load_by_name(
        "citation_audit", config.skills.citation_audit.version
    )
    assert loaded.manifest.implementation.endswith(":CitationAuditSkill")


def test_versioned_prompt_loader_loads_all_runtime_prompts() -> None:
    loader = PromptLoader()
    versions = load_runtime_config().skills.prompt_versions
    for name, version in versions.items():
        assert f"version: {version}" in loader.load(name, version)


def test_skill_schema_matches_pydantic_contract() -> None:
    config = load_runtime_config()
    loader = SkillLoader()
    research = loader.load(config.skills.evidence_research.manifest)
    audit = loader.load(config.skills.citation_audit.manifest)
    _assert_schema_root_matches(EvidenceResearchInput, research.input_schema)
    _assert_schema_root_matches(EvidenceResearchOutput, research.output_schema)
    _assert_schema_root_matches(CitationAuditInput, audit.input_schema)
    _assert_schema_root_matches(CitationAuditOutput, audit.output_schema)


def test_skill_fixtures_validate_against_pydantic_contracts() -> None:
    config = load_runtime_config()
    loader = SkillLoader()
    research = loader.load(config.skills.evidence_research.manifest).fixture
    audit = loader.load(config.skills.citation_audit.manifest).fixture
    EvidenceResearchInput.model_validate(research["input"])
    EvidenceResearchOutput.model_validate(research["output"])
    CitationAuditInput.model_validate(audit["input"])
    CitationAuditOutput.model_validate(audit["output"])


def test_skill_and_top_level_prompt_assets_do_not_drift() -> None:
    config = load_runtime_config()
    pairs = [
        (
            ROOT / "a5/skills/evidence_research/prompt_v0.2.0.md",
            ROOT / "prompts/evidence_research_v0.2.0.md",
        ),
        (
            ROOT / f"a5/skills/citation_audit/prompt_v{config.skills.citation_audit.prompt_version}.md",
            ROOT / f"prompts/citation_audit_v{config.skills.citation_audit.prompt_version}.md",
        ),
    ]
    for packaged, shared in pairs:
        assert packaged.read_text(encoding="utf-8") == shared.read_text(encoding="utf-8")
