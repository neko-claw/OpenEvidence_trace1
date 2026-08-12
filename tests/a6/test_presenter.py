from __future__ import annotations

from app.presenters.agent_run_presenter import paginate, present_reasons, present_timeline
from app.services.agent_service import AgentService


def test_paginate_clamps_indices_and_reports_count() -> None:
    items, index, count = paginate(list(range(9)), 99, 4)
    assert items == [8]
    assert index == 2
    assert count == 3


def test_trace_is_grouped_without_fabricating_streaming() -> None:
    payload = AgentService().analyze("Question", mode="replay", replay_case="PASS")
    timeline = present_timeline(payload.trace)
    assert [step.label for step in timeline] == [
        "范围与安全检查",
        "问题理解",
        "证据研究",
        "证据摘要",
        "主张生成",
        "引用审计",
        "发布门禁",
    ]
    assert all(step.status == "已完成" for step in timeline)


def test_warn_reasons_are_human_readable() -> None:
    payload = AgentService().analyze("Question", mode="replay", replay_case="WARN")
    reasons = present_reasons(payload)
    assert reasons
    assert any("证据" in item or "主张" in item for item in reasons)
