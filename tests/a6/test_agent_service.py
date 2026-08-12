from __future__ import annotations

from pathlib import Path

import pytest

from app.services.agent_service import AgentService


@pytest.mark.parametrize(
    ("case", "decision"),
    [("PASS", "PASS"), ("WARN", "WARN"), ("REFUSE", "REFUSE"), ("ERROR", "REFUSE")],
)
def test_service_projects_a5_replay_without_deciding(case: str, decision: str) -> None:
    payload = AgentService().analyze("A focused question", mode="replay", replay_case=case)
    assert payload.decision == decision
    assert payload.demo_mode is True
    assert payload.run_id
    assert payload.trace


def test_service_only_releases_cited_evidence_and_mock_is_safe() -> None:
    payload = AgentService().analyze("A focused question", mode="replay", replay_case="PASS")
    assert {item.evidence_id for item in payload.evidence} == {"E1", "E2"}
    assert all(item.mock for item in payload.evidence)
    assert all(item.url is None for item in payload.evidence)
    assert all(item.provenance == {"fixture": True} for item in payload.evidence)
    serialized = repr(payload.evidence).casefold()
    assert "doi" not in serialized
    assert "pmid" not in serialized
    assert "nct" not in serialized


def test_only_agent_service_imports_upstream_packages() -> None:
    root = Path("app")
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for package in ("a1", "a2", "a3", "retrieval", "a5", "deployment"):
            if f"from {package}" in text or f"import {package}" in text:
                if path.as_posix() != "app/services/agent_service.py" or package not in {"a5", "deployment"}:
                    offenders.append(f"{path}:{package}")
    assert offenders == []


def test_service_has_no_final_answer_cache() -> None:
    source = Path("app/services/agent_service.py").read_text(encoding="utf-8")
    assert "@st.cache_data" not in source
    assert source.count("@st.cache_resource") == 1
