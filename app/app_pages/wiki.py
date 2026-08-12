from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from app.components.pagination import render_pagination
from app.contracts import WikiTopic
from app.presenters.agent_run_presenter import paginate


@st.cache_data
def _load_topics() -> tuple[WikiTopic, ...]:
    path = Path(__file__).parents[1] / "data" / "wiki_topics.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(WikiTopic(
        slug=item["slug"], title=item["title"], subtitle=item["subtitle"],
        summary=item["summary"], related_questions=tuple(item["related_questions"]),
        evidence_note=item["evidence_note"],
    ) for item in raw)


def render() -> None:
    st.title("知识导航")
    st.markdown("用于组织和提出循证问题的知识导航层。")
    st.caption("原始证据始终具有最终权威性；本页面不会替代 A5 的检索与引用审计。")
    topics, page_index, page_count = paginate(_load_topics(), st.session_state.wiki_page_index, 2)
    st.session_state.wiki_page_index = page_index
    for topic in topics:
        with st.container(key=f"oe_topic_{topic.slug}", border=True):
            st.subheader(topic.title)
            st.caption(topic.subtitle)
            st.markdown(topic.summary)
            with st.expander("相关问题", icon=":material/help:"):
                for index, question in enumerate(topic.related_questions):
                    st.markdown(f"- {question}")
                    if st.button("分析此问题", key=f"wiki_{topic.slug}_{index}", type="tertiary"):
                        st.session_state.current_question = question
                        st.session_state.ask_input = question
                        st.session_state.current_agent_run = None
                        st.switch_page("app_pages/ask.py")
            st.caption(f"证据引用说明 · {topic.evidence_note}")
    render_pagination(
        state_key="wiki_page_index", page_index=page_index,
        page_count=page_count, key_prefix="wiki"
    )


render()
