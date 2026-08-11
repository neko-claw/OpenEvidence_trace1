from __future__ import annotations

import json
from pathlib import Path

import pytest

from a1.adapters import A1SafetyPolicyAdapter
from a1.export_schemas import rendered_schemas
from a1.models import (
    RetrievalTerminationInput,
    SafetyPolicyInput,
    SafetyPolicyOutput,
    TerminationAction,
)
from a1.policy import ReferenceSafetyPolicy, evaluate_retrieval_termination, load_termination_policy
from a5.domain.enums import SafetyDecision as A5SafetyDecision
from a5.domain.models import Question
from a5.ports.safety_policy import SafetyPolicy


ROOT = Path(__file__).resolve().parents[1]


def _fixture(name: str) -> dict:
    return json.loads((ROOT / "contracts" / "a1" / "v0.2" / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _fixture("safety_policy_cases.json")["cases"])
def test_safety_reference_cases(case: dict) -> None:
    result = ReferenceSafetyPolicy().assess(SafetyPolicyInput.model_validate(case["input"]))
    assert result.decision.value == case["expected_decision"]
    assert result.termination_action.value == case["expected_action"]
    SafetyPolicyOutput.model_validate(result.model_dump())


@pytest.mark.parametrize("case", _fixture("retrieval_termination_cases.json")["cases"])
def test_retrieval_termination_precedence(case: dict) -> None:
    result = evaluate_retrieval_termination(
        RetrievalTerminationInput.model_validate(case["input"])
    )
    assert result.action.value == case["expected_action"]


def test_termination_yaml_is_machine_valid_and_normalizes_decisions() -> None:
    contract = load_termination_policy(ROOT / "docs" / "a1" / "agent_termination_rules.yaml")
    assert {decision.value for decision in contract.release.decisions} == {"PASS", "WARN", "REFUSE"}
    assert contract.safety.policy_version == ReferenceSafetyPolicy.version
    assert contract.safety.default_decision.value == "UNKNOWN"
    assert contract.safety.unknown_action is TerminationAction.REFUSE


def test_checked_in_json_schemas_match_pydantic_source() -> None:
    for filename, expected in rendered_schemas().items():
        actual = (ROOT / "schemas" / "a1" / filename).read_text(encoding="utf-8")
        assert actual == expected


def test_a1_adapter_satisfies_a5_port_and_fails_closed_without_signals() -> None:
    adapter = A1SafetyPolicyAdapter()
    assert isinstance(adapter, SafetyPolicy)
    result = adapter.assess(Question(question_id="Q-MISSING", text="test question"))
    assert result.decision is A5SafetyDecision.UNKNOWN


def test_a1_adapter_allows_only_explicit_complete_allow_signals() -> None:
    signals = _fixture("safety_policy_cases.json")["cases"][0]["input"]
    result = A1SafetyPolicyAdapter().assess(
        Question(
            question_id="Q-ALLOW",
            text="test question",
            metadata={"a1_safety_signals": signals},
        )
    )
    assert result.decision is A5SafetyDecision.ALLOW


def test_a1_a5_crosswalk_documents_all_upstream_boundaries() -> None:
    crosswalk = (ROOT / "docs" / "a1" / "a1_a5_contract_crosswalk.md").read_text(
        encoding="utf-8"
    )
    for boundary in ("A1", "A2", "A3", "A4", "B2", "UNKNOWN", "REFUSE"):
        assert boundary in crosswalk
