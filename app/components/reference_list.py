from __future__ import annotations

import html

import streamlit as st

from app.contracts import EvidenceView


def render_reference_list(evidence: tuple[EvidenceView, ...]) -> None:
    with st.container(key="oe_references", border=True):
        st.subheader(":material/menu_book: 引用文献")
        if not evidence:
            st.caption("本次回答没有可发布的引用来源。")
            return
        for index, item in enumerate(evidence, start=1):
            title = html.escape(item.title)
            source = html.escape(_source(item.source_type))
            level = html.escape((item.evidence_level or "证据等级未知").replace("_", " "))
            identifier = html.escape(item.evidence_id.split("::", 1)[0])
            st.html(
                f"""
                <div class="oe-reference-row">
                  <div><span class="oe-reference-index">{index}.</span><span class="oe-reference-title">{title}</span></div>
                  <div class="oe-reference-meta">{source} · {item.year} · {level} · {identifier}</div>
                </div>
                """
            )
            if item.url and not item.mock:
                st.link_button(
                    "查看原始来源", item.url, icon=":material/open_in_new:",
                    type="tertiary", key=f"reference_link_{index}",
                )


def _source(value: str) -> str:
    return {
        "pubmed": "PubMed",
        "europe_pmc": "Europe PMC",
        "clinicaltrials": "ClinicalTrials.gov",
        "guideline": "临床指南",
    }.get(value.casefold(), value.replace("_", " "))
