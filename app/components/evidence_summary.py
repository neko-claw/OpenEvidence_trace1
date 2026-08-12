from __future__ import annotations

import html
from collections import Counter

import streamlit as st

from app.contracts import AgentPayload


def render_evidence_summary(payload: AgentPayload) -> None:
    with st.container(key="oe_evidence_summary", border=True):
        st.subheader(":material/analytics: 证据摘要")
        if not payload.evidence:
            st.caption("没有可发布的证据摘要。")
            return
        levels = Counter(item.evidence_level or "未知" for item in payload.evidence)
        sources = Counter(_source(item.source_type) for item in payload.evidence)
        dated = [item.published_at for item in payload.evidence if item.published_at]
        rows = (
            ("已引用证据", f"{len(payload.evidence)} 项"),
            ("证据类型", "、".join(f"{_level(k)} {v}" for k, v in levels.items())),
            ("来源覆盖", "、".join(f"{k} {v}" for k, v in sources.items())),
            ("适用人群", payload.structured_answer.applicability if payload.structured_answer else "未完整结构化"),
            ("最近更新", max(dated).strftime("%Y-%m") if dated else "未知"),
        )
        content = "".join(
            f'<div class="oe-metric-label">{html.escape(label)}</div>'
            f'<div class="oe-metric-value">{html.escape(value)}</div>'
            for label, value in rows
        )
        st.html(f'<div class="oe-metric-grid">{content}</div>')


def _source(value: str) -> str:
    return {
        "pubmed": "PubMed", "europe_pmc": "Europe PMC",
        "clinicaltrials": "ClinicalTrials.gov", "guideline": "临床指南",
    }.get(value.casefold(), value.replace("_", " "))


def _level(value: str) -> str:
    return {
        "guideline": "指南/共识", "systematic_review": "系统综述",
        "controlled_study": "对照研究", "clinical_trial_registry": "试验注册",
        "review": "综述", "study": "原始研究", "未知": "等级未知",
    }.get(value, value.replace("_", " "))
