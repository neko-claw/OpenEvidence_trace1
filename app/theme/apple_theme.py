from __future__ import annotations

import streamlit as st


def apply_apple_theme() -> None:
    """Small, scoped polish on top of the native Streamlit theme.

    The product brief explicitly requests an Apple-like visual treatment.
    Semantic colors and typography remain in ``.streamlit/config.toml``.
    """

    st.html(
        """
        <style>
        :root { color-scheme: light; }
        html, body, [class*="css"] { font-family: Inter, "SF Pro Display", "PingFang SC", "Microsoft YaHei", sans-serif; }
        [data-testid="stAppViewContainer"] { background: #F7F9FC; }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stSidebar"] {
          background: #FFFFFF; border-right: 1px solid #E4EAF3;
          min-width: 238px; max-width: 238px;
        }
        [data-testid="stSidebarContent"] { padding: 1.1rem .75rem 1.5rem; }
        [data-testid="stSidebarNav"] { padding-top: .8rem; }
        [data-testid="stSidebarNav"] a {
          border-radius: 10px; margin: .14rem 0; min-height: 42px;
          color: #38506F;
        }
        [data-testid="stSidebarNav"] a[aria-current="page"] {
          background: #EEF5FF; color: #1268D6; font-weight: 650;
        }
        .stMainBlockContainer { max-width: 1420px; padding: 1.6rem 2rem 4rem; }
        .oe-brand { display:flex; align-items:center; gap:.62rem; color:#114982; font-size:1.18rem; font-weight:750; margin:.2rem .35rem .2rem; }
        .oe-brand-orb { width:30px; height:30px; border-radius:50%; display:inline-block; background:linear-gradient(145deg,#3DCBFF 0%,#0786ED 48%,#1459D8 100%); box-shadow:0 5px 14px rgba(0,113,227,.24), inset 0 1px 3px rgba(255,255,255,.72); }
        .oe-brand-subtitle { margin:0 .35rem 1.15rem; color:#7A8BA3; font-size:.78rem; letter-spacing:.01em; }
        .st-key-oe_hero {
          background: #FFFFFF; border: 1px solid #DFE7F2;
          border-radius: 16px; padding: clamp(1.5rem, 4vw, 3.6rem);
          box-shadow: 0 8px 26px rgba(32,77,122,.055);
        }
        .st-key-oe_question_bar, .st-key-oe_answer, .st-key-oe_references,
        .st-key-oe_workflow_summary, .st-key-oe_evidence_summary,
        [class*="st-key-oe_evidence"], [class*="st-key-oe_topic"], [class*="st-key-oe_history"] {
          background: #FFFFFF; border-radius: 14px; padding: 1.15rem 1.25rem;
          box-shadow: 0 5px 18px rgba(32,77,122,.035); border: 1px solid #DFE7F2;
        }
        .st-key-oe_question_bar { background:linear-gradient(105deg,#F3F8FF 0%,#FAFCFF 100%); border-color:#D4E3F6; border-left:4px solid #2682EB; }
        .st-key-oe_references, .st-key-oe_evidence_summary, .st-key-oe_workflow_summary { margin-top:.85rem; }
        .st-key-oe_decision_pass { border-left: 5px solid #248A3D; }
        .st-key-oe_decision_warn { border-left: 5px solid #9A6700; }
        .st-key-oe_decision_refuse { border-left: 5px solid #C9342F; }
        [class*="st-key-oe_decision"] { padding:.75rem 1rem; border-radius:12px; background:#FFF; border:1px solid #DFE7F2; }
        [data-testid="stBaseButton-primary"] { font-weight: 650; box-shadow: 0 5px 16px rgba(0,113,227,.16); }
        [data-testid="stTextArea"] textarea { min-height: 112px; line-height: 1.55; }
        [data-testid="stExpander"] { background:#FFFFFF; border-radius:12px; border-color:#DFE7F2; }
        [class*="st-key-oe_trace_step"], [class*="st-key-oe_workflow_step"] { padding:.55rem .15rem .55rem 1rem; border-left:2px solid #B9D6F7; }
        .oe-section-kicker { color:#2468B2; font-size:.78rem; font-weight:700; letter-spacing:.045em; text-transform:uppercase; }
        .oe-metric-grid { display:grid; grid-template-columns:minmax(94px,.72fr) 1.4fr; gap:.58rem .8rem; font-size:.82rem; margin-top:.4rem; }
        .oe-metric-label { color:#7A8BA3; }
        .oe-metric-value { color:#263E5E; font-weight:550; overflow-wrap:anywhere; }
        .oe-reference-row { padding:.72rem 0; border-bottom:1px solid #EDF1F6; }
        .oe-reference-row:last-child { border-bottom:0; }
        .oe-reference-index { color:#1775DB; font-weight:700; margin-right:.45rem; }
        .oe-reference-title { color:#243C5A; font-weight:620; line-height:1.48; }
        .oe-reference-meta { color:#7A8BA3; font-size:.78rem; margin:.28rem 0 0 1.42rem; }
        h1, h2, h3 { letter-spacing:-.018em; }
        @media (prefers-reduced-motion: no-preference) {
          [data-testid="stBaseButton-primary"], [class*="st-key-oe_evidence"] { transition: transform .16s ease, box-shadow .16s ease; }
          [data-testid="stBaseButton-primary"]:hover, [class*="st-key-oe_evidence"]:hover { transform: translateY(-1px); }
        }
        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
        }
        @media (max-width: 900px) {
          [data-testid="stSidebar"] { min-width: 220px; max-width: 220px; }
          .stMainBlockContainer { padding:1rem 1rem 3rem; }
        }
        </style>
        """
    )
