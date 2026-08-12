from __future__ import annotations

import streamlit as st

from app.contracts import AgentPayload
from app.presenters.agent_run_presenter import present_reasons


def render_answer_card(payload: AgentPayload) -> None:
    with st.container(key="oe_answer", border=True):
        st.html('<div class="oe-section-kicker">Evidence-based answer</div>')
        st.subheader(":material/auto_awesome: 循证回答")
        if payload.error_message:
            st.markdown("当前证据服务未能安全完成本次分析。")
            st.caption(_safe_error_message(payload.error_code))
        elif payload.decision == "REFUSE":
            st.markdown("当前证据不足以支持可靠回答。请修改问题，或查看检索过程了解停止原因。")
        elif payload.structured_answer:
            answer = payload.structured_answer
            direct_citations = " ".join(
                f"`[{_citation_label(item)}]`" for item in answer.direct_evidence_ids
            )
            st.markdown(f"### 直接回答\n{answer.direct_answer} {direct_citations}")
            additional = answer.findings[1:]
            if additional:
                st.markdown("#### 进一步发现")
                for finding in additional:
                    citations = " ".join(
                        f"`[{_citation_label(item)}]`" for item in finding.evidence_ids
                    )
                    statement = finding.display_statement or finding.statement
                    st.markdown(f"{statement} {citations}")
                    if finding.display_statement:
                        with st.expander("核对来源原句"):
                            st.caption(finding.statement)
                    if finding.applicability:
                        st.caption(f"适用人群：{finding.applicability}")
            st.markdown("#### 适用范围")
            st.caption(answer.applicability)
            if answer.evidence_profile:
                st.markdown("#### 证据构成")
                st.caption(" · ".join(answer.evidence_profile))
            with st.container(horizontal=True, vertical_alignment="center"):
                tone = {"PASS": "green", "WARN": "orange", "REFUSE": "red"}[payload.decision]
                st.badge(payload.decision, color=tone, icon=":material/verified_user:")
                st.caption("发布状态来自 A5 可信门禁")
        else:
            st.markdown(payload.answer_text)

    reasons = present_reasons(payload)
    if reasons:
        st.subheader("证据限制" if payload.decision == "WARN" else "结果说明")
        for reason in reasons:
            st.markdown(f"- {reason}")


def _safe_error_message(error_code: str | None) -> str:
    return {
        "upstream_unavailable": "上游证据服务暂时不可用。",
        "internal_error": "系统内部步骤未完成，已停止发布回答。",
    }.get(error_code, "系统未能完成本次分析。")


def _citation_label(evidence_id: str) -> str:
    return evidence_id.split("::", 1)[0]
