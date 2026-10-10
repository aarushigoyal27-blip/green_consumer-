import streamlit as st

from src.ui import core_rule, header, read_doc

header("Explainability & Responsible AI", "Privacy, bias, hallucination, oversight, limitations")
core_rule()
st.markdown(read_doc("responsible_ai_note.md"))
