from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

# ``streamlit run app/main.py`` sets app/ as the script directory; add the repo
# root so ``app`` and the stable A5 package resolve identically in CLI/AppTest.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.state import initialize_state
from app.theme.apple_theme import apply_apple_theme

st.set_page_config(
    page_title="OpenEvidence",
    page_icon=":material/health_and_safety:",
    layout="wide",
    initial_sidebar_state="collapsed",
)
initialize_state(st.session_state)
apply_apple_theme()

with st.sidebar:
    st.html(
        """
        <div class="oe-brand">
          <span class="oe-brand-orb"></span>
          <span>OpenEvidence</span>
        </div>
        <div class="oe-brand-subtitle">可信医学证据工作台</div>
        """
    )
    if st.button(
        "新建问题", icon=":material/add:", type="primary",
        width="stretch", key="sidebar_new_query",
    ):
        st.session_state.current_agent_run = None
        st.session_state.current_question = ""
        st.session_state.ask_input = ""
        st.session_state.error_state = None
        st.rerun()

pages = [
    st.Page("app_pages/ask.py", title="提问", icon=":material/search:", default=True),
    st.Page("app_pages/evidence.py", title="引用来源", icon=":material/library_books:"),
    st.Page("app_pages/wiki.py", title="知识导航", icon=":material/book_2:"),
    st.Page("app_pages/about.py", title="关于", icon=":material/info:"),
]
navigation = st.navigation(pages, position="sidebar")
navigation.run()
