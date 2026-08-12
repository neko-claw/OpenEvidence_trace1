from __future__ import annotations

import streamlit as st


def render_pagination(*, state_key: str, page_index: int, page_count: int, key_prefix: str) -> None:
    if page_count <= 1:
        return
    with st.container(horizontal=True, horizontal_alignment="center", vertical_alignment="center"):
        if st.button("上一页", key=f"{key_prefix}_previous", disabled=page_index <= 0, icon=":material/chevron_left:"):
            st.session_state[state_key] = page_index - 1
            st.rerun()
        st.caption(f"第 {page_index + 1} / {page_count} 页")
        if st.button("下一页", key=f"{key_prefix}_next", disabled=page_index >= page_count - 1, icon=":material/chevron_right:"):
            st.session_state[state_key] = page_index + 1
            st.rerun()
