import json
from pathlib import Path

import pandas as pd
import streamlit as st

from ui import header, read_doc

header("Evaluation", "Validation-set metrics vs a simple baseline")

path = Path(__file__).parent / "results" / "eval.json"
if not path.exists():
    st.error("results/eval.json not found. Run `python evaluate.py` and include the results folder.")
    st.stop()
R = json.loads(path.read_text())
C, P = R["categoriser"], R["propensity"]
names = {"GP01": "EV propensity", "GP02": "Green Home propensity", "GP03": "Solar propensity", "GP04": "Paperless propensity"}

rows = [{"Component": "Transaction categoriser", "Metric": "Macro-F1", "Baseline (keyword rules)": round(C["baseline_macro_f1"], 3), "Model": round(C["macro_f1"], 3)}]
rows += [{"Component": names[g], "Metric": "PR-AUC", "Baseline (logistic regression)": round(p["logreg_pr_auc"], 3), "Model": round(p["model_pr_auc"], 3)} for g, p in P.items()]
df = pd.DataFrame(rows)
df["Baseline"] = df["Baseline (keyword rules)"].fillna(df["Baseline (logistic regression)"])
st.dataframe(df[["Component", "Metric", "Baseline", "Model"]], hide_index=True, width="stretch")
st.caption("Base rates of take-up: " + ", ".join(f"{names[g].split()[0]} {p['base_rate']:.1%}" for g, p in P.items())
           + ". Small synthetic data; the categoriser score is near-perfect because merchant names come from fixed templates.")

c1, c2, c3 = st.columns(3)
c1.metric("Carbon hand-checks passed", f"{sum(R['carbon_checks'].values())} / {len(R['carbon_checks'])}")
c2.metric("Scenario tests passed", f"{sum(s['pass'] for s in R['scenarios'])} / {len(R['scenarios'])}")
G = R["grounding"]
c3.metric("False figures caught", f"{G['injected_caught']} / {G['injected']}")

st.subheader("Scenario tests")
st.dataframe(pd.DataFrame(R["scenarios"]).rename(columns=str.title), hide_index=True, width="stretch")
with st.expander("Full evaluation report"):
    st.markdown(read_doc("eval_report.md"))
