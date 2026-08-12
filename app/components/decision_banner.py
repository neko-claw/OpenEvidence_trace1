from __future__ import annotations

import streamlit as st

from app.contracts import AgentPayload
from app.presenters.agent_run_presenter import present_decision


def render_decision_banner(payload: AgentPayload) -> None:
    view = present_decision(payload)
    with st.container(key=f"oe_decision_{payload.decision.casefold()}", border=True):
        st.subheader(f"{view.icon} {view.title}")
        st.caption(view.message)
        if payload.demo_mode:
            st.badge("测试数据", icon=":material/science:", color="blue")
