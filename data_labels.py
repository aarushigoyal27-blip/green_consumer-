import streamlit as st

from ui import header, read_doc

header("Data & labels", "Sources, schema, label rules, splits")

t1, t2 = st.tabs(["Data card", "Label rules"])
t1.markdown(read_doc("data_card.md"))
t2.markdown(read_doc("label_rules.md"))
