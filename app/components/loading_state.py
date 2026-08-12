from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

import streamlit as st


@contextmanager
def evidence_loading_state() -> Iterator[None]:
    with st.spinner("正在分析证据…", show_time=True):
        yield
