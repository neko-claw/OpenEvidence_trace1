from __future__ import annotations

import json

import streamlit as st

from app.contracts import EvidenceView


def render_evidence_card(evidence: EvidenceView, *, compact: bool = False) -> None:
    with st.container(key=f"oe_evidence_{evidence.evidence_id}", border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.subheader(f"证据 {_short_id(evidence.evidence_id)}")
            if evidence.mock:
                st.badge("测试数据", icon=":material/science:", color="blue")
        st.markdown(f"**{evidence.title}**")
        metadata = f"{_pretty_source(evidence.source_type)} · {evidence.year}"
        if evidence.evidence_level:
            metadata += f" · {evidence.evidence_level.replace('_', ' ')}"
        st.caption(metadata)

        if evidence.spans:
            span = evidence.spans[0]
            st.markdown(f"> {span.text}")
            if span.locator:
                st.caption(f"支持片段 · {span.locator}")
        elif not compact:
            st.caption("当前视图未包含可发布的支持片段。")

        if not compact:
            with st.expander("查看详情", icon=":material/description:"):
                st.markdown(f"**证据 ID：** `{evidence.evidence_id}`")
                st.markdown(f"**版本：** {evidence.version or '未知'}")
                if evidence.spans:
                    st.markdown("**支持片段**")
                    for span in evidence.spans:
                        st.markdown(f"- `{span.span_id}` — {span.locator or '定位信息不可用'}")
                st.markdown("**来源元数据**")
                st.code(json.dumps(evidence.source_metadata or {"状态": "未知"}, ensure_ascii=False, indent=2), language="json")
                st.markdown("**来源追溯信息**")
                st.code(json.dumps(evidence.provenance or {"状态": "未知"}, ensure_ascii=False, indent=2), language="json")
                if evidence.url and not evidence.mock:
                    st.link_button("打开原始来源", evidence.url, icon=":material/open_in_new:")


def _pretty_source(value: str) -> str:
    return {
        "guideline": "临床指南",
        "systematic_review": "系统综述",
        "primary_study": "原始研究",
        "clinical_trial": "临床试验",
        "pubmed": "PubMed",
        "europe_pmc": "Europe PMC",
        "clinicaltrials": "ClinicalTrials.gov",
    }.get(value.casefold(), value.replace("_", " ").strip())


def _short_id(value: str) -> str:
    return value.split("::", 1)[0]
