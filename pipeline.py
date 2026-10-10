"""The one function the UI calls:  insight(customer_id, product) -> contract payload (+ explanation).

Order is fixed by the core rule (ML predicts · rules decide eligibility · carbon engine computes · LLM explains):

    Customer 360 -> exclusion engine -> (if QUALIFIED) propensity model -> carbon engine -> grounded explanation
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score

import customer360 as c360
from carbon_engine import compute_impact
from exclusion_engine import evaluate_customer_targeting
from grounding import explain, validate

OPPORTUNITY_TO_GP = {"EV_FINANCE": "GP01", "GREEN_HOME": "GP02", "SOLAR_FINANCE": "GP03", "PAPERLESS": "GP04"}

# which Customer 360 features each model sees (no hidden traits, no labels)
MODEL_FEATURES = {
    "GP01": ["monthly_fuel_spend", "annual_mileage_km", "vehicle_age_years", "has_vehicle_loan", "public_transport_spend_12m", "income_num", "age_mid"],
    "GP02": ["monthly_elec_spend", "monthly_gas_spend", "baseline_gas_kwh", "home_improvement_spend_12m", "is_owner", "income_num", "age_mid"],
    "GP03": ["monthly_elec_spend", "baseline_electricity_kwh", "home_improvement_spend_12m", "is_owner", "income_num", "age_mid"],
    "GP04": ["paper_statement_ratio", "app_web_logins_3m", "income_num", "age_mid"],
}

# threshold rules from design_decisions.md section 4 (replace with top-3 SHAP -> code mapping later)
def reason_codes(gp: str, r: pd.Series) -> list[str]:
    out = []
    def add(cond, code):
        if bool(cond) and code not in out:
            out.append(code)
    if gp == "GP01":
        add(r["monthly_fuel_spend"] >= 150, "HIGH_FUEL_SPEND")
        add(r["annual_mileage_km"] >= 10000, "HIGH_ANNUAL_MILEAGE")
        add(r["has_ice_vehicle"], "EXISTING_VEHICLE")
        add(r["vehicle_age_years"] >= 8, "OLDER_VEHICLE")
        add(r["has_vehicle_loan"] == 1, "EXISTING_VEHICLE_LOAN")
    elif gp in ("GP02", "GP03"):
        t = c360.table()
        add(r["monthly_elec_spend"] >= t["monthly_elec_spend"].quantile(0.75), "HIGH_ELECTRICITY_SPEND")
        if gp == "GP02":
            add(r["monthly_gas_spend"] >= t["monthly_gas_spend"].quantile(0.75), "HIGH_GAS_SPEND")
            add(r["home_improvement_spend_12m"] > 0, "HOME_IMPROVEMENT_SPEND")
        add(r["is_owner"] == 1, "HOME_OWNER")
    else:
        add(r["paper_statement_ratio"] >= 0.5, "PAPER_STATEMENTS")
        add(r["app_web_logins_3m"] >= c360.table()["app_web_logins_3m"].median(), "HIGH_DIGITAL_ACTIVITY")
    return out[:3]


def _load_saved():
    import json
    import joblib
    d = Path(__file__).parent / "models"
    if all((d / f"{g}.joblib").exists() for g in MODEL_FEATURES) and (d / "metrics.json").exists():
        m = json.loads((d / "metrics.json").read_text())
        for v in m.values():
            v.setdefault("val_base_rate", None)
        return {g: joblib.load(d / f"{g}.joblib") for g in MODEL_FEATURES}, m
    return None


@lru_cache(maxsize=1)
def _models():
    saved = _load_saved()           # models/ written by train.py
    if saved:
        return saved
    """Fallback: train on the train split only, on ELIGIBLE pairs with a label. Report val PR-AUC for the Evaluation page."""
    t = c360.table().set_index("customer_id")
    lab = pd.read_csv(c360.ensure_data() / "takeup_labels.csv")
    lab = lab[lab["eligible"] & lab["took_up"].notna()]
    models, metrics = {}, {}
    for gp, feats in MODEL_FEATURES.items():
        d = lab[lab["product_id"] == gp].join(t[feats + ["split"]], on="customer_id")
        tr, va = d[d["split"] == "train"], d[d["split"] == "val"]
        m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, random_state=42)
        m.fit(tr[feats], tr["took_up"].astype(int))
        pr = average_precision_score(va["took_up"].astype(int), m.predict_proba(va[feats])[:, 1]) if len(va) else None
        models[gp] = m
        metrics[gp] = {"val_pr_auc": pr, "val_base_rate": float(va["took_up"].astype(int).mean()), "n_train": len(tr), "n_val": len(va)}
    return models, metrics


def metrics() -> dict:
    return _models()[1]


def _confidence(gp: str, r: pd.Series) -> float:
    """PLACEHOLDER: share of this model's inputs that are present. Swap for calibrated/ensemble uncertainty."""
    return round(float(r[MODEL_FEATURES[gp]].notna().mean()), 2)


def insight(customer_id: str, opportunity: str, with_explanation: bool = True, **llm_kwargs) -> dict:
    gp = OPPORTUNITY_TO_GP[opportunity]
    decision = evaluate_customer_targeting(c360.profile(customer_id), gp)        # 1. rules decide

    if decision["targeting_status"] == "QUALIFIED":
        row = c360.table().set_index("customer_id").loc[customer_id]
        x = row[MODEL_FEATURES[gp]].astype(float).to_frame().T
        decision["propensity"] = round(float(_models()[0][gp].predict_proba(x)[:, 1][0]), 3)   # 2. ML predicts
        decision["confidence"] = _confidence(gp, row)
        decision["reason_codes"] = reason_codes(gp, row)
        decision["impact"] = compute_impact(gp, c360.carbon_inputs(customer_id))             # 3. carbon engine computes

    decision["eligibility"] = "NOT_ASSESSED"
    if with_explanation:                                                                      # 4. LLM explains
        text = explain(decision, **llm_kwargs)
        decision["explanation"] = text
        decision["unsupported_numbers"] = [str(u) for u in validate(text, decision)]
    return decision


def score_all(opportunity: str) -> pd.DataFrame:
    """Scored table for the business dashboard (one row per customer for one product; no LLM calls)."""
    gp = OPPORTUNITY_TO_GP[opportunity]
    rows = []
    for cid in c360.table()["customer_id"]:
        d = insight(cid, opportunity, with_explanation=False)
        imp = (d.get("impact") or {}).get("value")
        rows.append({"customer_id": cid, "status": d["targeting_status"], "propensity": d["propensity"],
                     "impact_kg": imp, "region": None})
    df = pd.DataFrame(rows)
    return df.merge(c360.table()[["customer_id", "region", "split"]], on="customer_id", suffixes=("_x", "")).drop(columns="region_x")
