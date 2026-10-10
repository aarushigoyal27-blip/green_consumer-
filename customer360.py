"""Customer 360: ONE table, one row per customer, built only from data on/before the cutoff.

Every downstream component reads this table and nothing else:
  exclusion_engine  <- the contract fields (customer_profile_input in contract.json)
  propensity models <- the numeric feature columns (FEATURES below)
  carbon_engine     <- annual_* usage columns

Source today: the CSVs written by generate_data.py (./data). To plug in real/other data, change
only `load_raw()`; keep the output columns the same.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CUTOFF = "2026-06-30"

TENURE_MAP = {"OWNER_MORTGAGE": "MORTGAGED", "OWNER_OUTRIGHT": "OWNER", "RENT": "TENANT", "FAMILY": "LODGER"}
AGE_BAND_MID = {"18-29": 24, "30-44": 37, "45-59": 52, "60+": 68}

# Fields the generator does NOT produce. They are left null (-> INSUFFICIENT_DATA), never guessed.
# Set DEMO_FILL_MISSING=True ONLY for the demo so the app shows QUALIFIED customers; it is labelled
# as an assumption in the UI and the data card.
DEMO_FILL_MISSING = True
DEMO_DEFAULTS = {
    "marketing_consent": True, "account_status": "ACTIVE", "compliance_status": "CLEAR",
    "delinquency_status": "CURRENT", "is_in_arrears": False, "vulnerability_flag": False,
    "uk_resident": True, "country_code": "GB", "days_since_last_offer_decline": None,
    "property_type": "SEMI_DETACHED",   # generator has no property data; solar needs it
}

# numeric columns the propensity models may use (no label-derived or hidden-trait columns)
FEATURES = [
    "monthly_fuel_spend", "annual_mileage_km", "vehicle_age_years", "has_vehicle_loan",
    "monthly_elec_spend", "monthly_gas_spend", "baseline_electricity_kwh", "baseline_gas_kwh",
    "home_improvement_spend_12m", "public_transport_spend_12m",
    "paper_statement_ratio", "app_web_logins_3m", "income_num", "is_owner", "age_mid",
]


def _read(name: str, data_dir: Path) -> pd.DataFrame:
    return pd.read_csv(data_dir / name)


def load_raw(data_dir: Path = DATA) -> dict[str, pd.DataFrame]:
    """The ONLY place that knows where data comes from. Swap for DB / API calls."""
    return {n: _read(f"{n}.csv", data_dir) for n in
            ["customers", "vehicles", "energy_monthly", "digital_usage", "products_held", "transactions"]}


def build(data_dir: Path = DATA) -> pd.DataFrame:
    raw = load_raw(data_dir)
    cust, veh = raw["customers"], raw["vehicles"]
    energy, dig, held, tx = raw["energy_monthly"], raw["digital_usage"], raw["products_held"], raw["transactions"]

    # point-in-time guard: nothing after the cutoff may reach a feature
    tx = tx[pd.to_datetime(tx["date"]) <= CUTOFF]
    held = held[pd.to_datetime(held["opened_date"]) <= CUTOFF]

    df = cust.merge(veh, on="customer_id", how="left")

    # annualise energy from available months (a few months are missing on purpose)
    e = energy.groupby("customer_id").agg(
        elec_kwh_mean=("electricity_kwh", "mean"), elec_spend_mean=("electricity_spend_gbp", "mean"),
        gas_kwh_mean=("gas_kwh", "mean"), gas_spend_mean=("gas_spend_gbp", "mean"))
    df = df.merge(e, on="customer_id", how="left")
    df["baseline_electricity_kwh"] = df["elec_kwh_mean"] * 12
    df["baseline_gas_kwh"] = df["gas_kwh_mean"] * 12          # NaN if no gas connection
    df["monthly_elec_spend"], df["monthly_gas_spend"] = df["elec_spend_mean"], df["gas_spend_mean"]

    # spend by transaction category (12-month feature window)
    spend = tx.pivot_table(index="customer_id", columns="category", values="amount_gbp", aggfunc="sum").fillna(0)
    df = df.merge(spend.rename(columns=lambda c: f"spend_{c}"), on="customer_id", how="left")
    df["annual_fuel_spend"] = df["spend_Fuel"]
    df["monthly_fuel_spend"] = df["spend_Fuel"] / 12
    df["home_improvement_spend_12m"] = df["spend_Home Improvement"]
    df["public_transport_spend_12m"] = df["spend_Public Transport"]
    cnt = tx[pd.to_datetime(tx["date"]) >= "2026-01-01"].groupby("customer_id").size().rename("transaction_count_6m")
    df = df.merge(cnt, on="customer_id", how="left")
    df["transaction_count_6m"] = df["transaction_count_6m"].fillna(0).astype(int)

    # digital + statements
    d = dig.groupby("customer_id").agg(stm_total=("statements_total", "sum"), stm_paper=("statements_paper", "sum"))
    last3 = dig[dig["month"] >= "2026-04"].assign(l=lambda x: x.app_logins + x.web_logins).groupby("customer_id")["l"].sum()
    df = df.merge(d, on="customer_id", how="left").merge(last3.rename("digital_logins_90d"), on="customer_id", how="left")
    df["paper_statements_per_year"] = df["stm_paper"].astype(int)
    df["paper_statement_ratio"] = df["stm_paper"] / df["stm_total"]
    df["is_paperless"] = df["stm_paper"] == 0
    df["has_digital_banking"] = df["digital_logins_90d"] > 0
    df["app_web_logins_3m"] = df["digital_logins_90d"]

    # products held
    h = held.groupby("customer_id")["product_code"].apply(set)
    df["held"] = df["customer_id"].map(h).apply(lambda s: s if isinstance(s, set) else set())
    df["has_solar"] = df["held"].apply(lambda s: "GP03" in s)

    # vehicle / tenure
    vt = df["vehicle_type"].fillna("NONE")
    df["has_vehicle"] = vt != "NONE"
    df["is_ev_owner"] = vt == "EV"
    df["has_ice_vehicle"] = vt.isin(["PETROL", "DIESEL", "HYBRID"])
    df["vehicle_fuel_type"] = vt.str.lower().where(df["has_vehicle"], None)
    df["homeowner_status"] = df["tenure"].map(TENURE_MAP)
    df["is_owner"] = df["home_owner"].astype(int)
    df["income_num"] = df["income_band"].map({"Low": 0, "Mid": 1, "High": 2})
    df["age_mid"] = df["age_band"].map(AGE_BAND_MID)
    df["age"] = df["age_mid"]                # band midpoint; real data would have exact age
    df["has_vehicle_loan"] = df["has_vehicle_loan"].astype(float)

    df["data_cutoff_date"] = CUTOFF
    for k, v in (DEMO_DEFAULTS.items() if DEMO_FILL_MISSING else []):
        df[k] = v
    df["missing_core_inputs"] = df[["annual_mileage_km", "baseline_electricity_kwh"]].isna().sum(axis=1)
    return df


@lru_cache(maxsize=1)
def table() -> pd.DataFrame:
    return build()


PROFILE_FIELDS = [
    "customer_id", "data_cutoff_date", "homeowner_status", "is_ev_owner", "has_ice_vehicle", "has_vehicle",
    "vehicle_fuel_type", "annual_mileage_km", "annual_fuel_spend", "baseline_electricity_kwh", "baseline_gas_kwh",
    "paper_statements_per_year", "is_paperless", "has_digital_banking", "digital_logins_90d", "has_solar",
    "property_type", "property_epc_rating", "is_in_arrears", "delinquency_status", "vulnerability_flag", "age",
    "marketing_consent", "account_status", "transaction_count_6m", "uk_resident", "country_code",
    "compliance_status", "days_since_last_offer_decline",
]


def _clean(v):
    """numpy/pandas -> plain python, NaN -> None (the engines treat None as 'unknown')."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return None if np.isnan(v) else float(v)
    return v


def profile(customer_id: str) -> dict:
    """Contract-shaped input for exclusion_engine.evaluate_customer_targeting()."""
    row = table().set_index("customer_id").loc[customer_id]
    out = {"customer_id": customer_id}
    for f in PROFILE_FIELDS[1:]:
        out[f] = _clean(row[f]) if f in row.index else None   # absent column -> None (unknown)
    return out


def carbon_inputs(customer_id: str) -> dict:
    """Inputs for carbon_engine.compute_impact()."""
    r = table().set_index("customer_id").loc[customer_id]
    vt = r["vehicle_type"]
    return {
        "vehicle_type": vt if isinstance(vt, str) and vt != "NONE" else None,
        "annual_mileage_km": _clean(r["annual_mileage_km"]),
        "annual_fuel_spend_gbp": _clean(r["annual_fuel_spend"]),
        "annual_electricity_kwh": _clean(r["baseline_electricity_kwh"]),
        "annual_gas_kwh": _clean(r["baseline_gas_kwh"]),
        "paper_statements_per_year": _clean(r["paper_statements_per_year"]),
    }
