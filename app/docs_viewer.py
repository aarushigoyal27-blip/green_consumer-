import streamlit as st

from ui import DOCS, header

header("Doc templates", "Everything in docs/ – fill these in as work lands")
files = sorted(p.name for p in DOCS.glob("*.md") if p.name != "README.md")
choice = st.radio("Document", files, horizontal=True)
st.markdown((DOCS / choice).read_text(encoding="utf-8"))
