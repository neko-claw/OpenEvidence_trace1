from __future__ import annotations

import streamlit as st

from app.components.evidence_card import render_evidence_card
from app.components.pagination import render_pagination
from app.contracts import AgentPayload
from app.presenters.agent_run_presenter import paginate


def render() -> None:
    st.title("引用与原始来源")
    st.caption("仅展示当前回答中已发布主张实际引用的证据，可核对支持片段与来源。")
    payload: AgentPayload | None = st.session_state.current_agent_run
    if payload is None:
        st.info("请先分析一个问题，再查看相关证据。", icon=":material/library_books:")
        return
    if payload.demo_mode:
        st.badge("测试数据", icon=":material/science:", color="blue")
        st.caption("这些记录仅用于系统测试，不属于医学证据。")
    if not payload.evidence:
        st.caption("本次运行没有可发布的证据卡片。")
        return
    items, page_index, page_count = paginate(payload.evidence, st.session_state.page_index, 4)
    st.session_state.page_index = page_index
    for evidence in items:
        render_evidence_card(evidence)
    render_pagination(
        state_key="page_index", page_index=page_index,
        page_count=page_count, key_prefix="evidence"
    )


render()
