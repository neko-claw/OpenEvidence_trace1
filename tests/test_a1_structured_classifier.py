from __future__ import annotations

import json
from pathlib import Path

import pytest

from a1.adapters import A1SafetyPolicyAdapter
from a1.classifiers import StructuredSafetySignalClassifier
from a5.bootstrap import build_demo_workflow
from a5.domain.enums import Decision, SafetyDecision
from a5.domain.models import Question


ROOT = Path(__file__).parents[1]


class StaticTransport:
    def __init__(self, response: object = None, *, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def complete(self, **request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.response


def prediction(**changes: object) -> dict[str, object]:
    result: dict[str, object] = {
        "topic": "hypertension",
        "acute_emergency": False,
        "personal_diagnosis": False,
        "personalized_prescribing_or_dose_change": False,
        "prompt_injection_or_fabricated_reference": False,
        "identifiable_personal_data": False,
        "special_population": "none",
        "confidence": 0.99,
    }
    result.update(changes)
    return result


def classifier(transport: StaticTransport) -> StructuredSafetySignalClassifier:
    return StructuredSafetySignalClassifier(
        transport=transport,
        model="injected-safety-model",
        prompt_path=ROOT / "a1/classifiers/assets/safety_classifier_v0.1.0.md",
    )


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"acute_emergency": True}, SafetyDecision.DENY),
        ({"personal_diagnosis": True}, SafetyDecision.DENY),
        ({"personalized_prescribing_or_dose_change": True}, SafetyDecision.DENY),
        ({"prompt_injection_or_fabricated_reference": True}, SafetyDecision.DENY),
        ({"identifiable_personal_data": True}, SafetyDecision.DENY),
        ({"special_population": "pregnancy"}, SafetyDecision.DENY),
        ({}, SafetyDecision.ALLOW),
    ],
)
def test_structured_classifier_behavior(changes: dict[str, object], expected: SafetyDecision) -> None:
    transport = StaticTransport(prediction(**changes))
    result = A1SafetyPolicyAdapter(classifier=classifier(transport)).assess(
        Question(question_id="Q-A1", text="free text")
    )
    assert result.decision is expected
    assert "a1-safety-classifier-v0.1.0" in result.policy_version
    call = transport.calls[0]
    assert call["timeout_seconds"] == 5.0
    assert call["response_schema"]["additionalProperties"] is False
    assert set(json.loads(call["messages"][1]["content"])) == {"question_id", "text"}


@pytest.mark.parametrize(
    "transport",
    [
        StaticTransport(prediction(confidence=0.2)),
        StaticTransport(prediction(topic="unknown")),
        StaticTransport(prediction(special_population="unknown")),
        StaticTransport({"topic": "hypertension"}),
        StaticTransport({**prediction(), "extra": "drift"}),
        StaticTransport(prediction(topic="invalid")),
        StaticTransport(error=TimeoutError("timeout")),
    ],
)
def test_classifier_failures_become_unknown(transport: StaticTransport) -> None:
    result = A1SafetyPolicyAdapter(classifier=classifier(transport)).assess(
        Question(question_id="Q-UNKNOWN", text="free text")
    )
    assert result.decision is SafetyDecision.UNKNOWN
    assert "a1-safety-classifier-v0.1.0" in result.policy_version


class CountingRetriever:
    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, request):
        self.calls += 1
        raise AssertionError("Gate0 must stop before retrieval")


def test_gate0_unknown_stops_with_zero_tool_calls() -> None:
    retriever = CountingRetriever()
    workflow = build_demo_workflow()
    workflow._safety_policy = A1SafetyPolicyAdapter(
        classifier=classifier(StaticTransport(error=TimeoutError("timeout")))
    )
    workflow._retriever = retriever
    run = workflow.answer(Question(question_id="Q-STOP", text="free text"))
    assert run.decision is Decision.REFUSE
    assert retriever.calls == 0
    assert not [event for event in run.trace if event.tool_call_index is not None]


def test_policy_review_status_is_explicitly_pending() -> None:
    config = json.loads((ROOT / "config/a1_classifier.json").read_text(encoding="utf-8"))
    checklist = (ROOT / "docs/a1/safety_policy_review_checklist.md").read_text(encoding="utf-8")
    assert config["policy_status"] == "PENDING_REVIEW"
    assert "Approval record: not supplied" in checklist
