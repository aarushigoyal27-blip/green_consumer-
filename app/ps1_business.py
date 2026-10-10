import pandas as pd
import streamlit as st

from ui import header

header(
    "Business dashboard",
    "PS1 · FR6 business insights",
    todo="Replace mock frame with scored customer table; add region/trend filters.",
)

mock = pd.DataFrame(
    {
        "Product": ["EV Finance", "Green Home", "Solar Finance", "Paperless Banking"],
        "High-propensity customers": [0, 0, 0, 0],
        "Est. impact (t CO₂e/yr)": [0.0, 0.0, 0.0, 0.0],
    }
)

c1, c2, c3 = st.columns(3)
c1.metric("Customers analysed", "—")
c2.metric("Opportunities identified", "—")
c3.metric("Potential impact (t CO₂e)", "—")

st.subheader("Opportunities by product")
st.bar_chart(mock, x="Product", y="High-propensity customers")
st.dataframe(mock, width="stretch", hide_index=True)

st.subheader("Top segments")
st.caption("TODO: segment table (propensity, region, trend).")

st.subheader("Drill-down path")
st.markdown("**Customer → Opportunity → Evidence → Impact → Action**")
