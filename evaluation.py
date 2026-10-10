import pandas as pd
import streamlit as st

import pipeline
from ui import header, read_doc

header("Evaluation", "Validation-set metrics vs a simple baseline", todo="Transaction categoriser row still empty; add a baseline model.")
M = pipeline.metrics()

st.dataframe(
    pd.DataFrame(
        {
            "Component": ["Transaction categoriser", "EV propensity", "Green Home propensity", "Solar propensity", "Paperless propensity"],
            "Metric": ["Macro-F1", "PR-AUC", "PR-AUC", "PR-AUC", "PR-AUC"],
            "Baseline": [None] + [round(M[g]["val_base_rate"], 3) for g in ("GP01", "GP02", "GP03", "GP04")],
            "Model": [None] + [round(M[g]["val_pr_auc"], 3) for g in ("GP01", "GP02", "GP03", "GP04")],
        }
    ),
    hide_index=True,
    width="stretch",
)
with st.expander("Full report template"):
    st.markdown(read_doc("eval_report.md"))
