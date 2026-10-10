"""PS1 · Green Customer Insights Platform – Streamlit shell (Megathon X).
Run:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="PS1 Green Customer Insights", page_icon="🌱", layout="wide")

pages = {
    "Overview": [st.Page("home.py", title="Home", icon="🏠", default=True)],
    "Product": [
        st.Page("ps1_customer.py", title="Customer view", icon="👤"),
        st.Page("ps1_business.py", title="Business dashboard", icon="📊"),
    ],
    "Trust & Documentation": [
        st.Page("data_labels.py", title="Data & labels", icon="🗂️"),
        st.Page("evaluation.py", title="Evaluation", icon="🧪"),
        st.Page("explainability.py", title="Explainability & RAI", icon="🔍"),
        st.Page("architecture.py", title="Architecture", icon="🧱"),
        st.Page("docs_viewer.py", title="Doc templates", icon="📄"),
    ],
}
st.navigation(pages).run()
