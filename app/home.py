import streamlit as st

from ui import core_rule, header

header("🌱 Green Customer Insights Platform", "Megathon X: Singularity · PS1 · Lloyds")
core_rule()
st.write(
    "Turns customer transactions, products and behaviour into green financial opportunities "
    "(EV Finance, Green Home, Solar, Paperless), with estimated impact and clear explanations."
)
c1, c2 = st.columns(2)
c1.page_link("ps1_customer.py", label="Customer view →")
c2.page_link("ps1_business.py", label="Business dashboard →")

st.divider()
st.subheader("Submission checklist")
st.table(
    {
        "Item": [
            "A. Working prototype", "B. Source code + run instructions", "C. Trained models + inference code",
            "D. Preprocessing pipeline", "E. LLM implementation (prompts, model/API, eval approach)",
            "F. Architecture diagram", "G. Evaluation report (validation set)", "H. Responsible AI note",
            "I. Test-set predictions",
        ],
        "Where it lives": [
            "This app", "README.md", "TODO models/", "scripts/data/ (step6 + step7)", "grounding.py (explain + validate), scripts/benchmark_llm.py",
            "docs/architecture.mmd", "docs/eval_report.md", "docs/responsible_ai_note.md", "TODO predictions/",
        ],
    }
)
