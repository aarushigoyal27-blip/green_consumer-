import streamlit as st

import customer360 as c360
import pipeline
from ui import estimate_label, header

header("Customer view", "PS1 · FR5 customer insight, FR7 explainability")

ids = c360.table()["customer_id"].tolist()
customer = st.selectbox("Customer", ids[:200])
product = st.selectbox("Opportunity", list(pipeline.OPPORTUNITY_TO_GP))


@st.cache_data(show_spinner=False)
def get(cid, opp):
    return pipeline.insight(cid, opp)


d = get(customer, product)
imp = d.get("impact") or {}

with st.container(border=True):
    st.subheader(d["product_name"])
    if d["targeting_status"] == "EXCLUDED":
        st.error(f"Not offered: {', '.join(d['exclusion_reason_codes'])}", icon="🚫")
    elif d["targeting_status"] == "INSUFFICIENT_DATA":
        st.warning(f"Not enough data: missing {', '.join(d['missing_fields'])}", icon="❔")
    else:
        st.markdown("**Why you're seeing this:** " + (" · ".join(x.replace("_", " ").lower() for x in d["reason_codes"]) or "n/a"))
        c1, c2, c3 = st.columns(3)
        c1.metric("Propensity (ML)", d["propensity"])
        c2.metric("Confidence", d["confidence"])
        c3.metric("Potential annual impact", "not available" if imp.get("value") is None else f"{imp['value']:,.0f} kg CO₂e")
        estimate_label(f"Estimate · method: {imp.get('method', 'n/a')}")
        st.write(d["explanation"])
        if d["unsupported_numbers"]:
            st.error(f"Explanation contains numbers not in the data: {d['unsupported_numbers']}")
    st.caption(f"Data as of {d['cutoff_date']}")

with st.expander("Raw structured output (what the LLM is allowed to see)"):
    st.json({k: v for k, v in d.items() if k not in ("explanation", "unsupported_numbers")})
