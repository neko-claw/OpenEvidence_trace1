from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.services.agent_service import AgentService

APP = Path("app/main.py")


def _app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=15).run()


def _analyze(case: str, question: str = "A focused evidence question") -> AppTest:
    payload = AgentService().analyze(question, mode="replay", replay_case=case)
    at = AppTest.from_file(APP, default_timeout=15)
    at.session_state["current_agent_run"] = payload
    at.run()
    assert not at.exception
    return at


def _page(path: str, payload=None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=15)
    if payload is not None:
        at.session_state["current_agent_run"] = payload
    at.switch_page(path).run()
    assert not at.exception
    return at


def test_startup_home_and_question_input() -> None:
    at = _app()
    assert not at.exception
    assert at.title[0].value == "OpenEvidence"
    assert at.text_area[0].placeholder.startswith("高血压")
    assert "分析证据" in [button.label for button in at.button]
    assert len(at.selectbox) == 0


def test_question_submission_uses_configured_a5_service(monkeypatch) -> None:
    monkeypatch.setenv("OPENEVIDENCE_APP_MODE", "replay")
    from app.services.agent_service import get_agent_service

    get_agent_service.clear()
    at = _app()
    at.text_area[0].set_value("高血压证据问题")
    next(button for button in at.button if button.label == "分析证据").click().run()
    assert not at.exception
    assert at.session_state.current_agent_run.decision == "PASS"
    get_agent_service.clear()


@pytest.mark.parametrize(
    ("case", "expected", "banner"),
    [
        ("PASS", "PASS", "证据已核验"),
        ("WARN", "WARN", "已有证据，但存在限制"),
        ("REFUSE", "REFUSE", "证据不足，无法提供可靠回答"),
        ("ERROR", "REFUSE", "证据不足，无法提供可靠回答"),
    ],
)
def test_answer_states_are_driven_by_agent_run(case: str, expected: str, banner: str) -> None:
    at = _analyze(case)
    assert at.session_state.current_agent_run.decision == expected
    assert any(banner in item.value for item in at.subheader)


def test_pass_page_renders_verified_direct_answer_before_evidence() -> None:
    from app.contracts import FindingView, StructuredAnswerView

    payload = AgentService().analyze(
        "A focused evidence question", mode="replay", replay_case="PASS"
    )
    structured = StructuredAnswerView(
        direct_answer="Verified direct answer.",
        direct_evidence_ids=("E1",),
        findings=(FindingView(
            finding_id="F1",
            statement="Verified direct answer.",
            claim_ids=("C1",),
            evidence_ids=("E1",),
            display_statement=None,
            display_language=None,
            applicability=None,
            certainty="SUPPORTED_NOT_FORMALLY_GRADED",
        ),),
        applicability="Population not fully structured.",
        evidence_profile=("Systematic review 1",),
        uncertainties=(),
        composition_method="test",
    )
    at = AppTest.from_file(APP, default_timeout=15)
    at.session_state["current_agent_run"] = replace(payload, structured_answer=structured)
    at.run()
    assert not at.exception
    assert any("直接回答" in item.value for item in at.markdown)
    assert any(
        structured.direct_answer in item.value
        for item in at.markdown
    )
    assert any(item.value == ":material/menu_book: 引用文献" for item in at.subheader)
    assert any(item.value == ":material/account_tree: 分析过程" for item in at.subheader)
    assert any(item.value == ":material/analytics: 证据摘要" for item in at.subheader)


def test_sidebar_clinical_workbench_navigation_and_new_query() -> None:
    at = _app()
    labels = [button.label for button in at.button]
    assert "新建问题" in labels
    assert not at.exception


def test_warn_shows_limitations() -> None:
    at = _analyze("WARN")
    assert any(item.value == "证据限制" for item in at.subheader)
    assert any("证据" in item.value or "主张" in item.value for item in at.markdown)


def test_refuse_is_not_rendered_as_error() -> None:
    at = _analyze("REFUSE")
    assert len(at.error) == 0
    assert any("当前证据不足" in item.value for item in at.markdown)


def test_error_replay_exposes_safe_error_message() -> None:
    at = _analyze("ERROR")
    payload = at.session_state.current_agent_run
    assert payload.error_code == "upstream_unavailable"
    assert payload.error_message
    assert not at.exception


def test_evidence_page_renders_mock_label_spans_and_details() -> None:
    payload = AgentService().analyze("Question", mode="replay", replay_case="PASS")
    at = _page("app_pages/evidence.py", payload)
    assert at.title[0].value == "引用与原始来源"
    assert any("测试数据" in item.value for item in (*at.markdown, *at.caption))
    assert sum(item.value.startswith("**证据 ID：**") for item in at.markdown) == len(payload.evidence)
    assert any("Artificial outcome" in item.value for item in at.markdown)


def test_empty_evidence_page_is_graceful() -> None:
    payload = AgentService().analyze("Question", mode="replay", replay_case="REFUSE")
    at = _page("app_pages/evidence.py", payload)
    assert any("没有可发布" in item.value for item in at.caption)


def test_evidence_pagination_changes_page() -> None:
    payload = AgentService().analyze("Question", mode="replay", replay_case="PASS")
    evidence = tuple(
        replace(payload.evidence[index % 2], evidence_id=f"MOCK-E{index + 1}")
        for index in range(5)
    )
    at = _page("app_pages/evidence.py", replace(payload, evidence=evidence))
    assert any(button.label == "下一页" for button in at.button)
    next_button = next(button for button in at.button if button.label == "下一页")
    next_button.click().run()
    assert not at.exception
    assert at.session_state.page_index == 1


def test_wiki_is_navigation_layer_with_pagination() -> None:
    at = _page("app_pages/wiki.py")
    assert at.title[0].value == "知识导航"
    assert any("知识导航层" in item.value for item in at.markdown)
    assert any("原始证据" in item.value for item in at.caption)
    assert any(button.label == "下一页" for button in at.button)


def test_long_answer_renders_without_exception() -> None:
    payload = AgentService().analyze("Question", mode="replay", replay_case="PASS")
    long_text = "Verified evidence statement. " * 500
    at = AppTest.from_file(APP, default_timeout=15)
    at.session_state["current_agent_run"] = replace(payload, answer_text=long_text)
    at.run()
    assert not at.exception
    assert any(len(item.value) > 5000 for item in at.markdown)
