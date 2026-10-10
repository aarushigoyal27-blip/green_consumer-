import streamlit as st

from src.ui import estimate_label, header

header(
    "Customer view",
    "PS1 · FR5 customer insight, FR7 explainability",
    todo="Load customer from Customer 360; pull propensity, reason codes and impact from "
    "model/carbon-engine outputs; LLM text from structured JSON only.",
)

customer = st.selectbox("Customer", ["C10001", "C10002", "C10003"])
product = st.selectbox("Opportunity", ["EV_FINANCE", "GREEN_HOME", "SOLAR_FINANCE", "PAPERLESS"])

with st.container(border=True):
    st.subheader("An EV could cut your transport emissions")  # LLM output goes here
    st.markdown("**Why you're seeing this:** high fuel spend · high annual mileage · existing vehicle")
    c1, c2, c3 = st.columns(3)
    c1.metric("Propensity (ML)", "0.84")
    c2.metric("Confidence", "0.87")
    c3.metric("Potential annual impact", "[X] kg CO₂e")
    estimate_label("Estimate · method: carbon engine v0 (placeholder)")
    st.caption("Data as of [cutoff date]")
    st.button("Explore EV options", type="primary")

with st.expander("Raw structured output (what the LLM is allowed to see)"):
    st.json(
        {
            "customer_id": customer,
            "opportunity": product,
            "propensity": 0.84,
            "confidence": 0.87,
            "reason_codes": ["HIGH_FUEL_SPEND", "HIGH_ANNUAL_MILEAGE", "EXISTING_VEHICLE"],
            "impact_kg_co2e_per_year": None,
            "data_timestamp": None,
            "eligibility": "NOT_ASSESSED",
        }
    )
