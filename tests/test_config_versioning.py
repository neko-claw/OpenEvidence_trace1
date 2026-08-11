from pathlib import Path

from a5.domain.models import EvidenceRecord
from a5.gates.evidence_sufficiency import EvidenceSufficiencyGate
from a5.runtime_config import load_runtime_config


ROOT = Path(__file__).parents[1]


def records() -> list[EvidenceRecord]:
    return [
        EvidenceRecord(
            id="E1",
            content="A",
            source_type="guideline",
            title="A",
            retrieval_score=0.8,
            evidence_level="guideline",
            mock=True,
        ),
        EvidenceRecord(
            id="E2",
            content="B",
            source_type="systematic_review",
            title="B",
            retrieval_score=0.75,
            evidence_level="systematic_review",
            mock=True,
        ),
    ]


def test_threshold_is_loaded_from_yaml_and_changes_gate_behavior() -> None:
    strict = load_runtime_config(ROOT / "tests/fixtures/config_strict")
    result = EvidenceSufficiencyGate(strict.gates.gate2).evaluate(
        records(), freshness_required=False, budget_remaining=0
    )
    assert any("top_score below threshold" in reason for reason in result.reasons)


def test_versions_and_development_threshold_label_load_from_assets() -> None:
    config = load_runtime_config()
    assert config.agent.agent_version == "0.2.0"
    assert config.skills.evidence_research.version == "0.2.0"
    assert config.skills.prompt_versions["citation_audit"] == "0.2.0"
    assert config.gates.threshold_status == "development_default_not_clinically_validated"
