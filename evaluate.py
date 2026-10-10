"""Evaluation: python evaluate.py  ->  results/eval.json  (read by the Evaluation page and by build_docs.py)

Covers: transaction categoriser, propensity models vs baseline, carbon engine hand checks, scenario tests,
LLM grounding check, fairness by segment, latency.  Everything on the VALIDATION split unless stated.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, average_precision_score, brier_score_loss, f1_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

import customer360 as c360
import pipeline as pl
from carbon_engine import compute_impact
from exclusion_engine import evaluate_customer_targeting
from grounding import simulate_hallucination, validate

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)
R: dict = {}
data = c360.ensure_data()
T = c360.table().set_index("customer_id")

# ---------------------------------------------------------------- 1. transaction categoriser
tx = pd.read_csv(data / "transactions.csv", usecols=["customer_id", "merchant_raw", "category"])
tx["split"] = tx["customer_id"].map(T["split"])
tr, va = tx[tx.split == "train"].sample(60000, random_state=42), tx[tx.split == "val"].sample(20000, random_state=42)
KEYWORDS = [("Fuel", ["SHELL", "BP ", "ESSO", "PFS", "FUEL", "PETROL", "TEXACO", "GULF", "JET ", "MFG", "APPLEGREEN", "MURCO"]),
            ("Electricity", ["ELEC"]), ("Gas", [" GAS"]), ("Public Transport", ["TFL", "RAIL", "TRAIN", "BUS", "METRO", "LNER", "GWR", "OYSTER"]),
            ("Home Improvement", ["B&Q", "WICKES", "SCREWFIX", "HOMEBASE", "BUILDERS", "JOINERY", "GLAZING"]),
            ("Automotive", ["HALFORDS", "KWIK", "TYRE", "MOT", "CAR WASH", "DVLA", "RAC", "AA "]),
            ("Utilities", ["WATER", "BROADBAND", "VIRGIN", "DD"])]
def kw(s):
    s = s.upper()
    for cat, keys in KEYWORDS:
        if any(k in s for k in keys):
            return cat
    return "Other"
clf = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3), LogisticRegression(max_iter=300))
clf.fit(tr["merchant_raw"], tr["category"])
pred, base = clf.predict(va["merchant_raw"]), va["merchant_raw"].map(kw)
R["categoriser"] = {"n_val": len(va), "macro_f1": f1_score(va.category, pred, average="macro"), "accuracy": accuracy_score(va.category, pred),
                    "baseline_macro_f1": f1_score(va.category, base, average="macro"), "baseline_accuracy": accuracy_score(va.category, base)}

# ---------------------------------------------------------------- 2. propensity vs baseline
lab = pd.read_csv(data / "takeup_labels.csv")
lab = lab[lab["eligible"] & lab["took_up"].notna()]
models, _ = pl._models()
R["propensity"] = {}
for gp, feats in pl.MODEL_FEATURES.items():
    d = lab[lab.product_id == gp].join(T[feats + ["split"]], on="customer_id")
    tr_, va_ = d[d.split == "train"], d[d.split == "val"]
    y = va_["took_up"].astype(int)
    lr = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=1000)).fit(tr_[feats], tr_["took_up"].astype(int))
    prior = DummyClassifier(strategy="prior").fit(tr_[feats], tr_["took_up"].astype(int))
    p, pl_ = models[gp].predict_proba(va_[feats])[:, 1], lr.predict_proba(va_[feats])[:, 1]
    R["propensity"][gp] = {"n_val": len(va_), "base_rate": float(y.mean()),
        "model_pr_auc": average_precision_score(y, p), "model_roc_auc": roc_auc_score(y, p), "model_brier": brier_score_loss(y, p),
        "logreg_pr_auc": average_precision_score(y, pl_), "logreg_roc_auc": roc_auc_score(y, pl_), "logreg_brier": brier_score_loss(y, pl_),
        "prior_brier": brier_score_loss(y, prior.predict_proba(va_[feats])[:, 1])}

# ---------------------------------------------------------------- 3. carbon engine hand-checked
def close(a, b): return abs(a - b) < 0.11
checks = {
    "EV: 10,000 km petrol = 10000*(0.17048-0.06012)": close(compute_impact("GP01", {"vehicle_type": "PETROL", "annual_mileage_km": 10000})["value"], 1103.6),
    "EV: diesel 10,000 km = 10000*(0.17265-0.06012)": close(compute_impact("GP01", {"vehicle_type": "DIESEL", "annual_mileage_km": 10000})["value"], 1125.3),
    "EV: no vehicle -> insufficient": compute_impact("GP01", {"vehicle_type": None})["value"] is None,
    "Paperless: 12 statements = 12*10g*1198.24 kg/t": close(compute_impact("GP04", {"paper_statements_per_year": 12})["value"], 0.1),
    "Green Home: no usage -> insufficient": compute_impact("GP02", {})["value"] is None,
    "Solar: no electricity -> insufficient": compute_impact("GP03", {})["value"] is None,
}
R["carbon_checks"] = checks

# ---------------------------------------------------------------- 4. scenario tests
base_p = c360.profile("C10002")
def targ(profile, gp): return evaluate_customer_targeting(profile, gp)
sc = []
d = targ({**base_p, "annual_mileage_km": None, "annual_fuel_spend": None, "has_vehicle": None, "has_ice_vehicle": None}, "GP01")
sc.append(("Missing vehicle data", "INSUFFICIENT_DATA", d["targeting_status"]))
d = targ({**base_p, "is_ev_owner": True, "has_ice_vehicle": False}, "GP01")
sc.append(("EV owner with no petrol/diesel car, EV Finance", "EXCLUDED", d["targeting_status"]))
sc.append(("Tenant, Solar Finance", "EXCLUDED", targ({**base_p, "homeowner_status": "TENANT"}, "GP03")["targeting_status"]))
pp = c360.profile("C10001")   # customer on paper statements
assert targ(pp, "GP04")["targeting_status"] == "QUALIFIED"
sc.append(("Marketing opt-out", "EXCLUDED", targ({**pp, "marketing_consent": False}, "GP04")["targeting_status"]))
sc.append(("Unknown consent (null)", "INSUFFICIENT_DATA", targ({**pp, "marketing_consent": None}, "GP04")["targeting_status"]))
sc.append(("Insufficient impact data (no electricity)", "None", str(compute_impact("GP03", {"annual_electricity_kwh": None})["value"])))
a = targ(pp, "GP04")["targeting_status"]; b = targ({**pp, "is_paperless": True}, "GP04")["targeting_status"]
sc.append(("Customer goes paperless: output updates", "QUALIFIED -> EXCLUDED", f"{a} -> {b}"))
R["scenarios"] = [{"scenario": s, "expected": e, "observed": o, "pass": e == o} for s, e, o in sc]

# ---------------------------------------------------------------- 5. LLM grounding
ids = [i for i in T.index[:400]]
n = faithful = caught = injected = 0
for cid in ids:
    for opp in pl.OPPORTUNITY_TO_GP:
        dec = pl.insight(cid, opp, with_explanation=False)
        if dec["targeting_status"] != "QUALIFIED":
            continue
        from grounding import explain
        txt = explain(dec)
        n += 1
        faithful += len(validate(txt, dec)) == 0
        bad = simulate_hallucination(txt, ["This will save you 98765 kg CO2e per year."])
        injected += 1
        caught += len(validate(bad, dec)) > 0
        if n >= 200:
            break
    if n >= 200:
        break
R["grounding"] = {"n_explanations": n, "numeric_faithful": faithful, "injected": injected, "injected_caught": caught}

# ---------------------------------------------------------------- 6. fairness: recommendation rate by segment
t0 = time.time()
rows = []
for cid in T.index[:600]:
    for opp in pl.OPPORTUNITY_TO_GP:
        dd = pl.insight(cid, opp, with_explanation=False)
        rows.append((cid, opp, dd["targeting_status"], dd["propensity"]))
lat = (time.time() - t0) / len(rows) * 1000
sc_df = pd.DataFrame(rows, columns=["customer_id", "opp", "status", "p"]).join(T[["region", "age_band", "income_band", "tenure"]], on="customer_id")
sc_df["high"] = (sc_df.status == "QUALIFIED") & (sc_df.p >= 0.3)
R["fairness"] = {k: sc_df.groupby([k, "opp"])["high"].mean().unstack().round(3).to_dict() for k in ["income_band", "age_band", "tenure"]}
R["latency_ms_per_decision_no_llm"] = round(lat, 1)

# ---------------------------------------------------------------- data quality
cust = pd.read_csv(data / "customers.csv")
R["data"] = {"customers": len(cust), "transactions": int(len(tx)),
             "split_sizes": cust["split"].value_counts().to_dict(),
             "duplicate_customers": int(cust.customer_id.duplicated().sum()),
             "missing_mileage_among_vehicle_owners": float(T.loc[T.has_vehicle, "annual_mileage_km"].isna().mean()),
             "no_gas_share": float(T["baseline_gas_kwh"].isna().mean()),
             "no_vehicle_share": float((~T.has_vehicle).mean())}
json.dump(R, open(OUT / "eval.json", "w"), indent=1, default=float)
print(json.dumps({k: R[k] for k in ["categoriser", "carbon_checks", "scenarios", "grounding", "latency_ms_per_decision_no_llm", "data"]}, indent=1, default=float))
print(json.dumps(R["propensity"], indent=1))
