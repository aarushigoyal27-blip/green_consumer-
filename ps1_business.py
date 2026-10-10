import pandas as pd
import streamlit as st

import pipeline
from ui import header

header("Business dashboard", "PS1 · FR6 business insights")

THRESH = st.slider("High-propensity threshold", 0.05, 0.9, 0.3, 0.05)


@st.cache_data(show_spinner="Scoring customers…")
def scored() -> pd.DataFrame:
    frames = [pipeline.score_all(o).assign(product=o) for o in pipeline.OPPORTUNITY_TO_GP]
    return pd.concat(frames, ignore_index=True)


df = scored()
region = st.multiselect("Region", sorted(df["region"].unique()))
if region:
    df = df[df["region"].isin(region)]
hi = df[(df["status"] == "QUALIFIED") & (df["propensity"] >= THRESH)]

c1, c2, c3 = st.columns(3)
c1.metric("Customers analysed", df["customer_id"].nunique())
c2.metric("Opportunities identified", len(hi))
c3.metric("Potential impact (t CO₂e/yr)", f"{hi['impact_kg'].sum() / 1000:,.1f}")

summary = hi.groupby("product").agg(customers=("customer_id", "nunique"), impact_t=("impact_kg", lambda s: s.sum() / 1000)).reset_index()
st.subheader("Opportunities by product")
st.bar_chart(summary, x="product", y="customers")
st.dataframe(summary, width="stretch", hide_index=True)

st.subheader("Top segments (region × product)")
seg = hi.groupby(["region", "product"]).agg(customers=("customer_id", "count"), avg_propensity=("propensity", "mean")).reset_index()
st.dataframe(seg.sort_values("customers", ascending=False).head(15), width="stretch", hide_index=True)

st.subheader("Drill-down path")
st.markdown("**Customer → Opportunity → Evidence → Impact → Action**")
