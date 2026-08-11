import json
from pathlib import Path

from a5.runtime_config import load_runtime_config


ROOT = Path(__file__).parents[1]


def test_demo_trace_artifacts_cover_required_control_flow() -> None:
    payload = json.loads((ROOT / "artifacts/demo_trace.json").read_text(encoding="utf-8"))
    states = [event["state"] for event in payload["trace"]]
    for required in (
        "GATE0",
        "SELECT_SKILL",
        "RETRIEVE",
        "GATE1",
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
    config = load_runtime_config()
    text = (ROOT / "artifacts/demo_trace.txt").read_text(encoding="utf-8")
    assert f"Gate0@{config.gates.gate0_version}" in text
    assert f"Gate1@{config.gates.gate1_version}" in text
    assert f"evidence_research@{config.skills.evidence_research.version}" in text
    assert f"citation_audit@{config.skills.citation_audit.version}" in text
    assert f"Gate5@{config.gates.gate5_version}" in text
    assert f"Gate6@{config.gates.gate6_version}" in text
