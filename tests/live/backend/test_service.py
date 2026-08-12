from __future__ import annotations

import json

import pytest

from a5.domain.enums import Decision
from deployment.track1_backend import (
    BackendServiceConfig,
    LiveCompositionUnavailable,
    build_service,
    check_readiness,
)
from deployment.track1_backend.service import JsonlTraceSink


def test_replay_and_mock_are_explicitly_separate(tmp_path) -> None:
    replay = build_service("replay", trace_sink=JsonlTraceSink(tmp_path / "runs.jsonl"))
    mock = build_service("mock")
    assert replay.answer("ignored", replay_case="PASS").decision is Decision.PASS
    mock_run = mock.answer("synthetic", replay_case="PASS")
    assert mock_run.retrieved_evidence and all(item.mock for item in mock_run.retrieved_evidence)
    rows = (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1 and json.loads(rows[0])["decision"] == "PASS"


def test_live_construction_fails_closed_without_mock_fallback() -> None:
    readiness = check_readiness()
    assert readiness.live_ready is False
    with pytest.raises(LiveCompositionUnavailable) as caught:
        build_service("live")
    assert caught.value.readiness.blockers
    assert "mock" not in caught.value.readiness.components.values()


def test_request_limits_and_safe_health() -> None:
    service = build_service("replay", config=BackendServiceConfig(max_question_chars=3))
    with pytest.raises(ValueError, match="size limit"):
        service.answer("four")
    health = service.health()
    assert health == {
        "status": "ok",
        "mode": "replay",
        "config_version": "track1-backend-v0.1.0",
        "live_ready": False,
    }


def test_mode_dependency_isolation() -> None:
    with pytest.raises(ValueError, match="cannot receive live dependencies"):
        from a5.facade import BackendDependencies
        from a5.bootstrap import build_default_workflow

        build_service("replay", dependencies_factory=lambda: BackendDependencies(build_default_workflow()))
