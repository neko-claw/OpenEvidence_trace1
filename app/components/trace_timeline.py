from __future__ import annotations

import streamlit as st

from app.contracts import AgentPayload
from app.presenters.agent_run_presenter import present_timeline


def render_trace_timeline(payload: AgentPayload, *, expanded: bool = False) -> None:
    with st.expander("技术轨迹", expanded=expanded, icon=":material/account_tree:"):
        st.caption("以下步骤来自本次完整运行记录；当前展示最终状态，不伪造实时进度。")
        steps = present_timeline(payload.trace)
        if not steps:
            st.caption("A5 未返回轨迹事件。")
            return
        for index, step in enumerate(steps):
            with st.container(key=f"oe_trace_step_{index}"):
                icon = ":material/check_circle:" if step.status == "已完成" else ":material/cancel:"
                st.markdown(f"{icon} **{step.label}**")
                st.caption(f"{step.result} · {step.latency_ms:.1f} ms")
        st.caption(
            f"运行 {payload.run_id} · Agent 版本 {payload.agent_version} · 门禁配置 {payload.gate_config_version}"
        )


def render_workflow_summary(payload: AgentPayload) -> None:
    """Compact, human-readable final run timeline for the result rail."""

    with st.container(key="oe_workflow_summary", border=True):
        st.subheader(":material/account_tree: 分析过程")
        steps = present_timeline(payload.trace)
        if not steps:
            st.caption("本次运行没有可展示的过程记录。")
            return
        for index, step in enumerate(steps):
            with st.container(key=f"oe_workflow_step_{index}"):
                icon = ":material/check_circle:" if step.status == "已完成" else ":material/cancel:"
                st.markdown(f"{icon} **{step.label}**")
                st.caption(f"{step.result} · {step.latency_ms:.1f} ms")
        with st.expander("查看完整技术轨迹", icon=":material/terminal:"):
            st.caption(
                f"运行 {payload.run_id} · Agent {payload.agent_version} · "
                f"门禁 {payload.gate_config_version}"
            )
            for event in payload.trace:
                detail = event.decision or (
                    f"输出 {event.output_count} 项" if event.output_count is not None else "已记录"
                )
                st.markdown(f"`{event.state}` · {detail} · {event.latency_ms:.1f} ms")
