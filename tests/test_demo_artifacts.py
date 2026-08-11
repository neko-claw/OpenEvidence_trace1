import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_demo_trace_artifacts_cover_required_control_flow() -> None:
    payload = json.loads((ROOT / "artifacts/demo_trace.json").read_text(encoding="utf-8"))
    states = [event["state"] for event in payload["trace"]]
    for required in (
        "GATE0",
        "SELECT_SKILL",
        "RETRIEVE",
        "GATE2",
        "SUMMARIZE_EVIDENCE",
        "GENERATE_CLAIMS",
        "CLAIM_SPLITTER",
        "AUDIT_CITATIONS",
        "GATE5",
        "GATE6",
    ):
        assert required in states
    retrieve_events = [event for event in payload["trace"] if event["state"] == "RETRIEVE"]
    assert [event["tool_call_index"] for event in retrieve_events] == [1, 2]
    assert [event["tool_budget_remaining"] for event in retrieve_events] == [2, 1]
    assert payload["decision"] == "PASS"
    assert payload["runtime_config_snapshot"]["gates"]["threshold_status"].startswith(
        "development_default"
    )


def test_readable_demo_trace_contains_gate_and_skill_versions() -> None:
    text = (ROOT / "artifacts/demo_trace.txt").read_text(encoding="utf-8")
    assert "Gate0@0.2.0" in text
    assert "evidence_research@0.2.0" in text
    assert "citation_audit@0.2.0" in text
    assert "Gate5@0.2.0" in text
    assert "Gate6@0.2.0" in text
