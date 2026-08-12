from __future__ import annotations

import streamlit as st


def render() -> None:
    st.title("关于 OpenEvidence")
    st.markdown("**面向临床医生、医学生与科研人员的可信循证问答工具。**")
    st.markdown(
        "A6 只负责展示 A5 的输出，不负责检索证据、生成主张、审计引用，"
        "也不负责决定通过、警告或拒答。"
    )
    with st.container(border=True):
        st.subheader("工作方式")
        st.markdown("用户问题 → 问题结构化 → 多源检索 → 证据综合 → 带引用回答 → 原始来源")
    with st.container(border=True):
        st.subheader("重要限制")
        st.markdown(
            "仅供教学研究，不用于临床诊疗。系统不能替代医生判断；"
            "任何测试数据都会明确标识，不得将其视为医学证据。"
        )
    st.caption("未来可接入 A5 事件流；控制逻辑仍保留在 A5，不会迁入 A6。")


render()
