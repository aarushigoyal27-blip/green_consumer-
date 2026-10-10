import pandas as pd
import streamlit as st

from ui import header, read_doc

header("Evaluation", "Validation-set metrics vs a simple baseline", todo="Populate from the eval script's output files.")

st.dataframe(
    pd.DataFrame(
        {
            "Component": ["Transaction categoriser", "EV propensity", "Green Home propensity", "Solar propensity", "Paperless propensity"],
            "Metric": ["Macro-F1", "PR-AUC", "PR-AUC", "PR-AUC", "PR-AUC"],
            "Baseline": [None] * 5,
            "Model": [None] * 5,
        }
    ),
    hide_index=True,
    width="stretch",
)
with st.expander("Full report template"):
    st.markdown(read_doc("eval_report.md"))
