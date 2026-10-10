import streamlit as st

from ui import DOCS, header, mermaid

header("Architecture", "Source: docs/architecture.mmd")
code = (DOCS / "architecture.mmd").read_text(encoding="utf-8")
mermaid(code, height=720)
with st.expander("Mermaid source"):
    st.code(code, language="text")
