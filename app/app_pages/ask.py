from __future__ import annotations

import streamlit as st

from app.components.answer_card import render_answer_card
from app.components.decision_banner import render_decision_banner
from app.components.evidence_card import render_evidence_card
from app.components.loading_state import evidence_loading_state
from app.components.pagination import render_pagination
from app.components.trace_timeline import render_trace_timeline, render_workflow_summary
from app.components.reference_list import render_reference_list
from app.components.evidence_summary import render_evidence_summary
from app.contracts import AgentPayload, HistoryItem
from app.presenters.agent_run_presenter import paginate
from app.services.agent_service import get_agent_service
from app.state import restore_history_item, store_run

_EXAMPLES = (
    "当前指南对成年高血压患者的血压控制目标有何建议？",
    "2 型糖尿病患者降低心血管事件风险有哪些近期随机试验证据？",
    "房颤卒中预防中 DOAC 与华法林的疗效和安全性如何比较？",
)


def render() -> None:
    payload: AgentPayload | None = st.session_state.current_agent_run
    if payload is None:
        _render_home()
    else:
        _render_result(payload)
    _render_history()


def _render_home() -> None:
    with st.container(key="oe_hero", border=True, horizontal_alignment="center"):
        st.title("OpenEvidence", text_alignment="center")
        st.markdown("有来源、可追溯的循证回答", text_alignment="center")
        st.caption(
            "面向心脑血管病、高血压、血脂异常与糖尿病的循证问答。"
            "先给出可核验结论，再按需展开原始证据。",
            text_alignment="center",
        )
        _render_question_form()

        if st.session_state.error_state:
            st.error(st.session_state.error_state, icon=":material/error:")

    st.space("medium")
    st.subheader("从这些问题开始")
    labels = ("指南与目标", "心血管结局试验", "治疗比较")
    cols = st.columns(3)
    for index, (column, label, question) in enumerate(zip(cols, labels, _EXAMPLES, strict=True)):
        with column.container(border=True, height="stretch"):
            st.markdown(f"**{label}**")
            st.caption(question)
            st.button(
                "使用此问题", key=f"example_{index}", type="tertiary",
                on_click=_set_question, args=(question,),
            )


def _render_question_form() -> None:
    with st.form("question_form", border=False):
        st.text_area(
            "医学证据问题",
            key="ask_input",
            placeholder="高血压患者血压控制目标有哪些最新证据？",
            label_visibility="collapsed",
            max_chars=2000,
        )
        submitted = st.form_submit_button(
            "分析证据", type="primary", icon=":material/search:", width="stretch"
        )
    if submitted:
        question = st.session_state.ask_input.strip()
        if not question:
            st.warning("请先输入一个明确的问题。", icon=":material/info:")
            return
        _run_analysis(question)


def _run_analysis(question: str) -> None:
    try:
        with evidence_loading_state():
            payload = get_agent_service().analyze(question)
        store_run(st.session_state, payload)
        st.rerun()
    except Exception as exc:  # Presentation boundary: A5 has already failed closed.
        st.session_state.error_state = "公开证据服务暂时未能完成本次请求，请稍后重试。"
        st.session_state.current_agent_run = None
        st.session_state["_a6_exception_type"] = type(exc).__name__


def _render_result(payload: AgentPayload) -> None:
    with st.container(key="oe_question_bar", border=True):
        with st.container(horizontal=True, vertical_alignment="top"):
            st.markdown(":material/account_circle:")
            with st.container():
                st.markdown(f"**{payload.question}**")
                st.caption(payload.started_at.astimezone().strftime("%Y-%m-%d %H:%M · 已完成证据分析"))
            if st.button("新问题", icon=":material/add:", type="secondary", key="result_new_query"):
                st.session_state.current_agent_run = None
                st.session_state.error_state = None
                st.rerun()

    if payload.decision == "REFUSE":
        render_decision_banner(payload)
        render_answer_card(payload)
        _render_refuse_actions(payload)
        render_trace_timeline(payload)
        return

    main_col, rail_col = st.columns([1.72, 0.88], gap="medium", vertical_alignment="top")
    with main_col:
        render_decision_banner(payload)
        render_answer_card(payload)
        render_reference_list(payload.evidence)
    with rail_col:
        render_workflow_summary(payload)
        render_evidence_summary(payload)


def _render_refuse_actions(payload: AgentPayload) -> None:
    with st.container(horizontal=True):
        if st.button("修改问题", icon=":material/edit:", type="primary"):
            st.session_state.current_agent_run = None
            st.rerun()
        st.caption("展开下方“技术轨迹”，可查看已完成的检索过程。")


def _render_history() -> None:
    history: list[HistoryItem] = st.session_state.history
    if not history:
        return
    st.space("large")
    st.subheader("最近分析")
    items, page_index, page_count = paginate(history, st.session_state.history_page_index, 3)
    st.session_state.history_page_index = page_index
    for item in items:
        with st.container(key=f"oe_history_{item.run_id}", border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                color = {"PASS": "green", "WARN": "orange", "REFUSE": "red"}[item.decision]
                st.badge(item.decision, color=color)
                st.caption(item.created_at.strftime("%Y-%m-%d %H:%M"))
            st.markdown(item.question)
            if st.button("查看分析", key=f"history_{item.run_id}", type="tertiary"):
                restore_history_item(st.session_state, item)
                st.rerun()
    render_pagination(
        state_key="history_page_index", page_index=page_index,
        page_count=page_count, key_prefix="history"
    )


def _set_question(question: str) -> None:
    st.session_state.current_question = question
    st.session_state.ask_input = question


render()
