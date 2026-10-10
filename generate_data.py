"""PS1 · Step 6 – Synthetic data generator.

Run:   python generate_data.py                 # 2000 customers -> ./data
       python generate_data.py --n 5000 --out data

Deterministic: the same SEED always gives byte-identical files.
Needs only numpy + pandas.

Design (see design_decisions.md):
  * Hidden traits per customer (car dependence, eco-mindedness, digital comfort,
    energy-use level) + visible attributes (region, income, tenure) drive EVERYTHING else.
  * Feature window  : 2025-07-01 .. 2026-06-30   (12-month lookback, cutoff 2026-06-30)
  * Outcome window  : 2026-07-01 .. 2026-12-31   (take-up measured ONLY here)
  * Transaction category = the category of the merchant template that produced it (ground truth).
  * Take-up: p = sigmoid(intercept + weighted traits/derived features + noise), only for
    ELIGIBLE customer x product pairs. Ineligible pairs get no label (empty).
  * Split by customer 70/15/15.

Files written to --out:
  customers.csv  vehicles.csv  energy_monthly.csv  digital_usage.csv  products_held.csv
  transactions.csv  takeup_labels.csv  merchant_templates.csv  generation_report.json
  _hidden/traits.csv   <- ground-truth latent traits. NEVER use as model features.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------------ config
SEED = 42  # single seed for the whole project
CUTOFF = pd.Timestamp("2026-06-30")
MONTHS = pd.period_range("2025-07", "2026-06", freq="M")  # feature window (12 months)
OUTCOME_START = pd.Timestamp("2026-07-01")
OUTCOME_END = pd.Timestamp("2026-12-31")
SPLIT_FRACS = (0.70, 0.15, 0.15)
TARGET_PREVALENCE = {"GP01": 0.08, "GP02": 0.10, "GP03": 0.07, "GP04": 0.25}  # among ELIGIBLE
PRODUCTS = {"GP01": "EV_FINANCE", "GP02": "GREEN_HOME", "GP03": "SOLAR_FINANCE", "GP04": "PAPERLESS"}
EV_REPLACEMENT_AGE = 8  # EX01: an EV older than this has a "replacement use case"

# region: (weight, car_dependence_shift, P(gas connected), gas_multiplier, public_transport_boost)
REGIONS = {
    "North East": (0.04, 0.05, 0.90, 1.10, 0.0),
    "North West": (0.11, 0.02, 0.90, 1.05, 0.0),
    "Yorkshire and The Humber": (0.08, 0.03, 0.90, 1.05, 0.0),
    "East Midlands": (0.07, 0.06, 0.90, 1.00, 0.0),
    "West Midlands": (0.09, 0.04, 0.90, 1.00, 0.0),
    "East of England": (0.09, 0.06, 0.90, 0.95, 0.0),
    "London": (0.13, -0.20, 0.85, 0.90, 1.0),
    "South East": (0.14, 0.05, 0.90, 0.95, 0.0),
    "South West": (0.09, 0.08, 0.85, 0.95, 0.0),
    "Wales": (0.05, 0.08, 0.85, 1.05, 0.0),
    "Scotland": (0.08, 0.00, 0.80, 1.15, 0.2),
    "Northern Ireland": (0.03, 0.08, 0.10, 0.90, 0.0),
}
CITIES = ["LONDON", "MANCHESTER", "LEEDS", "BIRMINGHAM", "BRISTOL", "GLASGOW", "CARDIFF", "NEWCASTLE",
          "SHEFFIELD", "NOTTINGHAM", "LEICESTER", "BELFAST", "EDINBURGH", "READING", "NORWICH", "EXETER"]

# unit prices used to turn kWh / litres into £ (synthetic, documented in the data card)
PRICE = {"elec_kwh": 0.27, "elec_standing_day": 0.55, "gas_kwh": 0.07, "gas_standing_day": 0.30,
         "petrol_litre": 1.45, "diesel_litre": 1.52}
LITRES_PER_KM = {"PETROL": 0.075, "DIESEL": 0.065, "HYBRID": 0.045}

# ------------------------------------------------- merchant templates (ground-truth labels)
# {n}=store number, {city}=city, {ref}=reference. Boundary rules (see label_rules.md):
#   * car wash / servicing / MOT / tyres = Automotive; pump fuel = Fuel
#   * single-fuel energy account (ELEC / GAS in the name) = Electricity / Gas
#   * supplier billing both fuels, water, broadband = Utilities
TEMPLATES: dict[str, list[str]] = {
    "Fuel": ["SHELL {n} {city}", "BP CONNECT {n}", "ESSO {n} {city}", "TESCO PFS {n}", "SAINSBURYS FUEL {n}",
             "ASDA PETROL {n}", "MORRISONS PETROL {n}", "TEXACO {n} {city}", "GULF {n}", "JET {n} {city}",
             "MFG {n}", "APPLEGREEN {n}", "MOTO {n} FUEL", "MURCO {n}", "CERTAS FUEL {n} {city}"],
    "Electricity": ["OCTOPUS ENERGY ELEC DD {ref}", "EDF ENERGY ELECTRICITY DD {ref}", "E.ON NEXT ELEC DD {ref}",
                    "OVO ENERGY ELEC DD {ref}", "SCOTTISH POWER ELEC DD {ref}", "BRITISH GAS ELECTRICITY ONLY DD",
                    "UTILITA ELECTRIC DD {ref}", "SO ENERGY ELEC DD {ref}", "SHELL ENERGY ELEC DD {ref}",
                    "GREEN NETWORK ENERGY ELEC {ref}", "OPUS ENERGY ELEC DD {ref}", "EBICO ELEC DD {ref}",
                    "UNITED GRID ELEC DD {ref}", "PUREPLANET ELEC DD {ref}", "ENSTROM POWER ELEC DD {ref}"],
    "Gas": ["OCTOPUS ENERGY GAS DD {ref}", "EDF ENERGY GAS DD {ref}", "E.ON NEXT GAS DD {ref}",
            "OVO ENERGY GAS DD {ref}", "SCOTTISH POWER GAS DD {ref}", "BRITISH GAS GAS ONLY DD",
            "UTILITA GAS DD {ref}", "SO ENERGY GAS DD {ref}", "SHELL ENERGY GAS DD {ref}",
            "GREEN NETWORK ENERGY GAS {ref}", "OPUS ENERGY GAS DD {ref}", "EBICO GAS DD {ref}",
            "UNITED GRID GAS DD {ref}", "PUREPLANET GAS DD {ref}", "ENSTROM GAS DD {ref}"],
    "Utilities": ["OCTOPUS ENERGY DD {ref}", "BRITISH GAS DUAL FUEL DD", "EDF ENERGY DD {ref}", "OVO ENERGY DD {ref}",
                  "E.ON NEXT DD {ref}", "THAMES WATER DD", "SEVERN TRENT WATER DD", "UNITED UTILITIES DD",
                  "ANGLIAN WATER DD", "YORKSHIRE WATER DD", "DWR CYMRU WELSH WATER", "SCOTTISH WATER DD",
                  "SOUTHERN WATER DD", "BT BROADBAND DD {ref}", "VIRGIN MEDIA DD {ref}"],
    "Public Transport": ["TFL TRAVEL CH", "TRAINLINE {ref}", "NATIONAL RAIL {n}", "NORTHERN RAIL {ref}", "LNER {ref}",
                         "GWR {ref}", "AVANTI WEST COAST {ref}", "STAGECOACH {city}", "FIRST BUS {city}",
                         "ARRIVA {city}", "METROLINK {ref}", "TYNE AND WEAR METRO", "SCOTRAIL {ref}",
                         "TFW RAIL {ref}", "OYSTER AUTOTOP"],
    "Home Improvement": ["B&Q {n} {city}", "WICKES {n}", "SCREWFIX {n}", "TOOLSTATION {n}", "HOMEBASE {n}",
                         "TRAVIS PERKINS {city}", "JEWSON {city}", "SELCO BUILDERS WAREHOUSE", "PLUMBCENTER {n}",
                         "HOWDENS JOINERY {n}", "DULUX DECORATOR CENTRE {n}", "INSULATION SUPPLIES LTD {ref}",
                         "DOUBLE GLAZING INSTALLER {ref}", "WICKES KITCHENS {city}", "IRONMONGERY DIRECT {ref}"],
    "Automotive": ["HALFORDS {n}", "KWIK FIT {city}", "ATS EUROMASTER {n}", "NATIONAL TYRES {city}",
                   "DVLA VEHICLE TAX", "MOT TEST CENTRE {city}", "CAR WASH {city}", "HAND CAR WASH {n}",
                   "SHELL CAR WASH {n}", "AA MEMBERSHIP {ref}", "RAC BREAKDOWN {ref}", "EURO CAR PARTS {n}",
                   "HALFORDS AUTOCENTRE {n}", "VW SERVICE CENTRE {city}", "FORD DEALER SERVICE {city}"],
    "Other": ["TESCO STORES {n}", "SAINSBURYS S/MKTS {n}", "ASDA {n}", "AMAZON.CO.UK*{ref}", "NETFLIX.COM",
              "SPOTIFY {ref}", "COSTA COFFEE {n}", "PRET A MANGER {n}", "DELIVEROO {ref}", "BOOTS {n}",
              "GREGGS {n}", "NEXT RETAIL {n}", "PAYPAL *{ref}", "ODEON CINEMAS {city}", "PUREGYM {city}"],
}
DUAL_FUEL = ["OCTOPUS ENERGY DD {ref}", "BRITISH GAS DUAL FUEL DD", "EDF ENERGY DD {ref}", "OVO ENERGY DD {ref}",
             "E.ON NEXT DD {ref}"]  # subset of Utilities templates that are dual-fuel supplier bills
WATER = ["THAMES WATER DD", "SEVERN TRENT WATER DD", "UNITED UTILITIES DD", "ANGLIAN WATER DD", "YORKSHIRE WATER DD",
         "DWR CYMRU WELSH WATER", "SCOTTISH WATER DD", "SOUTHERN WATER DD"]
BROADBAND = ["BT BROADBAND DD {ref}", "VIRGIN MEDIA DD {ref}"]


# ------------------------------------------------------------------ helpers
def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def zscore(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    s = s.fillna(s.median())
    sd = s.std(ddof=0)
    return (s - s.mean()) / (sd if sd > 0 else 1.0)


def auc(score: np.ndarray, y: np.ndarray) -> float:
    """Rank-based ROC-AUC (no sklearn needed)."""
    r = pd.Series(score).rank().to_numpy()
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def fill_template(rng, tmpl: str) -> str:
    out = tmpl
    if "{n}" in out:
        out = out.replace("{n}", str(int(rng.integers(100, 9999))))
    if "{city}" in out:
        out = out.replace("{city}", CITIES[int(rng.integers(len(CITIES)))])
    if "{ref}" in out:
        out = out.replace("{ref}", "".join(rng.choice(list("ABCDEFGHJKLMNPQRSTUVWXYZ23456789"), 6)))
    return out


def noisy(rng, s: str) -> str:
    """Bank-statement style noise: prefixes, casing, truncation."""
    prefix = ["", "", "", "CARD PAYMENT TO ", "POS ", "VIS "][int(rng.integers(6))]
    r = rng.random()
    if r < 0.10:
        s = s.title()
    elif r < 0.16 and len(s) > 14:
        s = s[: int(rng.integers(12, len(s)))]
    return prefix + s


# ------------------------------------------------------------------ tables
def gen_customers(rng, n):
    names = list(REGIONS)
    weights = np.array([REGIONS[r][0] for r in names])
    region = rng.choice(names, n, p=weights / weights.sum())
    income = rng.choice(["Low", "Mid", "High"], n, p=[0.30, 0.50, 0.20])
    inc_num = pd.Series(income).map({"Low": 0, "Mid": 1, "High": 2}).to_numpy()
    age = rng.choice(["18-29", "30-44", "45-59", "60+"], n, p=[0.20, 0.30, 0.28, 0.22])
    p_own = sigmoid(-1.0 + 0.7 * inc_num + 0.9 * np.isin(age, ["45-59", "60+"]) + 0.4 * (age == "30-44"))
    owner = rng.random(n) < p_own
    mort = rng.random(n) < 0.60
    tenure = np.where(owner, np.where(mort, "OWNER_MORTGAGE", "OWNER_OUTRIGHT"),
                      np.where(rng.random(n) < 0.8, "RENT", "FAMILY"))
    car_shift = np.array([REGIONS[r][1] for r in region])
    car_dep = np.clip(rng.beta(2.5, 2.5, n) + car_shift + 0.10 * np.isin(age, ["30-44", "45-59"]), 0, 1)
    eco = np.clip(rng.beta(2, 2.5, n) + 0.06 * inc_num, 0, 1)
    digital = np.clip(rng.beta(3, 2, n) - 0.30 * (age == "60+") + 0.10 * (age == "18-29"), 0, 1)
    energy_f = rng.lognormal(0, 0.30, n) * np.where(owner, 1.15, 0.85)
    gas_p = np.array([REGIONS[r][2] for r in region])
    gas = rng.random(n) < gas_p
    p_digital = sigmoid(-0.3 + 3.5 * (digital - 0.5))
    u = rng.random(n)
    stmt = np.where(u < p_digital * 0.85, "DIGITAL", np.where(u < p_digital * 0.85 + 0.15, "MIXED", "PAPER"))
    ids = [f"C{10001 + i}" for i in range(n)]
    cust = pd.DataFrame({"customer_id": ids, "region": region, "age_band": age, "income_band": income,
                         "tenure": tenure, "home_owner": owner, "gas_connected": gas, "statement_pref": stmt})
    hidden = pd.DataFrame({"customer_id": ids, "car_dependence": car_dep.round(4), "eco_mindedness": eco.round(4),
                           "digital_comfort": digital.round(4), "energy_use_factor": energy_f.round(4)})
    # customer-level split BEFORE anything else is built on top
    perm = rng.permutation(n)
    cut1, cut2 = int(SPLIT_FRACS[0] * n), int((SPLIT_FRACS[0] + SPLIT_FRACS[1]) * n)
    split = np.empty(n, dtype=object)
    split[perm[:cut1]], split[perm[cut1:cut2]], split[perm[cut2:]] = "train", "val", "test"
    cust["split"] = split
    return cust, hidden, inc_num


def gen_vehicles(rng, cust, hidden, inc_num):
    n = len(cust)
    cd, eco = hidden["car_dependence"].to_numpy(), hidden["eco_mindedness"].to_numpy()
    owns = rng.random(n) < sigmoid(1.2 + 4.0 * (cd - 0.5))  # ~75% own a vehicle (UK-plausible)
    p_ev = sigmoid(-3.3 + 2.2 * eco + 0.4 * inc_num)
    u = rng.random(n)
    ice_split = rng.random(n) < 0.6
    vtype = np.where(u < p_ev, "EV", np.where(u < p_ev + 0.08, "HYBRID", np.where(ice_split, "PETROL", "DIESEL")))
    vtype = np.where(owns, vtype, "NONE")
    age = np.where(vtype == "EV", rng.gamma(2.0, 1.3, n), rng.gamma(3.0, 3.0, n))
    age = np.clip(np.round(age), 0, 20)
    km = np.clip(rng.lognormal(9.4 + 0.9 * (cd - 0.5), 0.30, n), 1500, 45000)
    km = np.round(km, -2)
    loan = rng.random(n) < np.where(age < 5, 0.25, 0.05)
    veh = pd.DataFrame({"customer_id": cust["customer_id"], "vehicle_type": vtype, "vehicle_age_years": age,
                        "annual_mileage_km": km, "has_vehicle_loan": loan})
    none = veh["vehicle_type"] == "NONE"
    veh.loc[none, ["vehicle_age_years", "annual_mileage_km"]] = np.nan
    veh.loc[none, "has_vehicle_loan"] = False
    # missing data injected on purpose (scenario tests)
    veh.loc[(~none) & (rng.random(n) < 0.03), "annual_mileage_km"] = np.nan
    veh.loc[(~none) & (rng.random(n) < 0.02), "vehicle_age_years"] = np.nan
    return veh


def gen_energy(rng, cust, hidden):
    rows = []
    months = np.array([p.month for p in MONTHS])
    wg = 1 + 0.85 * np.cos(2 * np.pi * (np.arange(1, 13) - 1) / 12)  # gas: winter-heavy
    share_g = (wg / wg.sum())
    we = 1 + 0.12 * np.cos(2 * np.pi * (np.arange(1, 13) - 1) / 12)  # electricity: flatter
    share_e = (we / we.sum())
    gas_mult = cust["region"].map(lambda r: REGIONS[r][3]).to_numpy()
    for i, c in enumerate(cust.itertuples(index=False)):
        f = hidden.at[i, "energy_use_factor"]
        ann_e = 2700 * f
        ann_g = 11500 * f * gas_mult[i] if c.gas_connected else 0.0
        keep = rng.random(12) > 0.04  # ~4% of months missing
        ne = rng.normal(1, 0.08, 12)
        ng = rng.normal(1, 0.08, 12)
        for k, m in enumerate(months):
            if not keep[k]:
                continue
            ek = ann_e * share_e[m - 1] * ne[k]
            e_spend = ek * PRICE["elec_kwh"] + 30 * PRICE["elec_standing_day"]
            if c.gas_connected:
                gk = ann_g * share_g[m - 1] * ng[k]
                g_spend = gk * PRICE["gas_kwh"] + 30 * PRICE["gas_standing_day"]
            else:
                gk, g_spend = np.nan, np.nan
            rows.append((c.customer_id, str(MONTHS[k]), round(ek, 1), round(e_spend, 2),
                         round(gk, 1) if c.gas_connected else np.nan,
                         round(g_spend, 2) if c.gas_connected else np.nan))
    return pd.DataFrame(rows, columns=["customer_id", "month", "electricity_kwh", "electricity_spend_gbp",
                                       "gas_kwh", "gas_spend_gbp"])


def gen_digital(rng, cust, hidden):
    rows = []
    n_acc = rng.integers(1, 4, len(cust))
    for i, c in enumerate(cust.itertuples(index=False)):
        d = hidden.at[i, "digital_comfort"]
        for p in MONTHS:
            total = int(n_acc[i])
            paper = {"PAPER": total, "DIGITAL": 0, "MIXED": int(rng.integers(1, total + 1)) if total > 1 else 1}[c.statement_pref]
            if c.statement_pref == "MIXED" and total == 1:
                paper = int(rng.random() < 0.5)
            rows.append((c.customer_id, str(p), int(rng.poisson(2 + 40 * d)), int(rng.poisson(1 + 8 * d)),
                         total, paper))
    return pd.DataFrame(rows, columns=["customer_id", "month", "app_logins", "web_logins",
                                       "statements_total", "statements_paper"])


def gen_products(rng, cust, veh, inc_num, hidden):
    rows = []
    start = pd.Timestamp("2015-01-01")
    span = (CUTOFF - start).days

    def add(cid, code):
        rows.append((cid, code, (start + pd.Timedelta(days=int(rng.integers(0, span)))).date().isoformat()))

    eco = hidden["eco_mindedness"].to_numpy()
    for i, c in enumerate(cust.itertuples(index=False)):
        add(c.customer_id, "CURRENT_ACCOUNT")
        if rng.random() < 0.45 + 0.15 * inc_num[i]:
            add(c.customer_id, "SAVINGS")
        if rng.random() < sigmoid(-2.0 + 0.9 * inc_num[i] + 1.0 * eco[i]):
            add(c.customer_id, "INVESTMENTS")
        if c.tenure == "OWNER_MORTGAGE":
            add(c.customer_id, "MORTGAGE")
        if veh.at[i, "has_vehicle_loan"]:
            add(c.customer_id, "VEHICLE_LOAN")
        if rng.random() < 0.12:
            add(c.customer_id, "PERSONAL_LOAN")
        # existing green products (drive EX04 "already holds")
        if veh.at[i, "vehicle_type"] == "EV" and rng.random() < 0.35:
            add(c.customer_id, "GP01")
        if c.home_owner and rng.random() < 0.03:
            add(c.customer_id, "GP02")
        if c.home_owner and rng.random() < 0.03:
            add(c.customer_id, "GP03")
        if c.statement_pref == "DIGITAL" and rng.random() < 0.5:
            add(c.customer_id, "GP04")
    return pd.DataFrame(rows, columns=["customer_id", "product_code", "opened_date"])


def gen_transactions(rng, cust, hidden, veh, energy):
    """One row per transaction. Category = category of the template that produced it."""
    rows = []
    t_idx = {k: np.array(v, dtype=object) for k, v in TEMPLATES.items()}
    en = energy.set_index(["customer_id", "month"])
    en_keys = set(en.index)
    for i, c in enumerate(cust.itertuples(index=False)):
        cid = c.customer_id
        cd, eco = hidden.at[i, "car_dependence"], hidden.at[i, "eco_mindedness"]
        v = veh.iloc[i]
        london = REGIONS[c.region][4]
        # stable merchants per customer
        dual = bool(c.gas_connected and rng.random() < 0.5)
        sup_e = TEMPLATES["Electricity"][int(rng.integers(15))]
        sup_g = TEMPLATES["Gas"][int(rng.integers(15))]
        sup_d = DUAL_FUEL[int(rng.integers(len(DUAL_FUEL)))]
        water = WATER[int(rng.integers(len(WATER)))]
        bband = BROADBAND[int(rng.integers(len(BROADBAND)))] if rng.random() < 0.8 else None
        dd_day = int(rng.integers(1, 28))
        for p in MONTHS:
            m = str(p)
            dim = p.days_in_month

            def add(day, tmpl, amount, cat):
                d = pd.Timestamp(year=p.year, month=p.month, day=int(min(max(day, 1), dim)))
                rows.append((cid, d.date().isoformat(), noisy(rng, fill_template(rng, tmpl)), round(float(amount), 2), cat))

            # --- fuel
            if v["vehicle_type"] in LITRES_PER_KM and not np.isnan(v["annual_mileage_km"]):
                price = PRICE["diesel_litre"] if v["vehicle_type"] == "DIESEL" else PRICE["petrol_litre"]
                spend = v["annual_mileage_km"] / 12 * LITRES_PER_KM[v["vehicle_type"]] * price * rng.uniform(0.85, 1.15)
            elif v["vehicle_type"] in LITRES_PER_KM:  # mileage missing -> still drives, use typical
                spend = 12000 / 12 * LITRES_PER_KM[v["vehicle_type"]] * PRICE["petrol_litre"]
            else:
                spend = 0.0
            n_fills = int(round(spend / 55)) if spend > 0 else 0
            if n_fills > 0:
                amts = np.clip(rng.normal(spend / n_fills, 8, n_fills), 12, 110)
                for a in amts:
                    add(int(rng.integers(1, dim + 1)), TEMPLATES["Fuel"][int(rng.integers(15))], a, "Fuel")
            # --- energy direct debits (only months with a meter reading)
            if (cid, m) in en_keys:
                r = en.loc[(cid, m)]
                if dual:
                    add(dd_day, sup_d, r["electricity_spend_gbp"] + r["gas_spend_gbp"], "Utilities")
                else:
                    add(dd_day, sup_e, r["electricity_spend_gbp"], "Electricity")
                    if c.gas_connected and not np.isnan(r["gas_spend_gbp"]):
                        add(dd_day, sup_g, r["gas_spend_gbp"], "Gas")
            # --- water / broadband
            add(dd_day, water, rng.normal(32, 6), "Utilities")
            if bband:
                add(dd_day, bband, rng.normal(30, 4), "Utilities")
            # --- public transport
            lam = 1.5 + 14 * (1 - cd) * (0.5 + eco) + 8 * london
            for _ in range(int(rng.poisson(lam))):
                add(int(rng.integers(1, dim + 1)), TEMPLATES["Public Transport"][int(rng.integers(15))],
                    rng.uniform(2, 28), "Public Transport")
            # --- home improvement (owners mostly)
            p_hi = 0.04 + (0.22 * (0.4 + eco) if c.home_owner else 0.03)
            if rng.random() < p_hi:
                for _ in range(int(rng.integers(1, 4))):
                    add(int(rng.integers(1, dim + 1)), TEMPLATES["Home Improvement"][int(rng.integers(15))],
                        rng.lognormal(4.2, 0.8), "Home Improvement")
            # --- automotive (vehicle owners)
            if v["vehicle_type"] != "NONE" and rng.random() < 0.25:
                add(int(rng.integers(1, dim + 1)), TEMPLATES["Automotive"][int(rng.integers(15))],
                    rng.lognormal(4.3, 0.7), "Automotive")
            # --- everything else
            for _ in range(int(rng.poisson(14))):
                add(int(rng.integers(1, dim + 1)), TEMPLATES["Other"][int(rng.integers(15))],
                    rng.lognormal(2.7, 0.8), "Other")
    tx = pd.DataFrame(rows, columns=["customer_id", "date", "merchant_raw", "amount_gbp", "category"])
    tx = tx.sort_values(["customer_id", "date"], kind="stable").reset_index(drop=True)
    tx.insert(0, "txn_id", [f"T{j + 1:08d}" for j in range(len(tx))])
    return tx


# ------------------------------------------------------------------ eligibility + take-up
def eligibility(cust, veh, held) -> pd.DataFrame:
    """Hard exclusion rules (design_decisions.md §3). First matching rule wins."""
    held_set = set(zip(held["customer_id"], held["product_code"]))
    out = []
    for i, c in enumerate(cust.itertuples(index=False)):
        v = veh.iloc[i]
        for pid in PRODUCTS:
            reason = None
            if pid == "GP01":
                if v["vehicle_type"] == "NONE":
                    reason = "NO_VEHICLE"
                elif v["vehicle_type"] == "EV" and not (v["vehicle_age_years"] >= EV_REPLACEMENT_AGE):
                    reason = "ALREADY_OWNS_EV"
            elif pid in ("GP02", "GP03") and not c.home_owner:
                reason = "NOT_HOME_OWNER"
            elif pid == "GP04" and c.statement_pref == "DIGITAL":
                reason = "ALREADY_PAPERLESS"
            if reason is None and (c.customer_id, pid) in held_set:
                reason = "ALREADY_HOLDS_PRODUCT"
            out.append((c.customer_id, pid, reason is None, reason))
    return pd.DataFrame(out, columns=["customer_id", "product_id", "eligible", "exclusion_reason"])


def solve_intercept(base: np.ndarray, target: float) -> float:
    lo, hi = -15.0, 15.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if sigmoid(base + mid).mean() > target:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def gen_takeup(rng, cust, hidden, veh, inc_num, energy, tx, digital, held):
    elig = eligibility(cust, veh, held)
    cid = cust["customer_id"]
    fuel_m = tx[tx.category == "Fuel"].groupby("customer_id")["amount_gbp"].sum().reindex(cid).fillna(0) / 12
    hi_spend = tx[tx.category == "Home Improvement"].groupby("customer_id")["amount_gbp"].sum().reindex(cid).fillna(0)
    e_ann = energy.groupby("customer_id")["electricity_kwh"].mean().reindex(cid).fillna(0) * 12
    g_ann = energy.groupby("customer_id")["gas_kwh"].mean().reindex(cid).fillna(0) * 12
    app = digital.groupby("customer_id")["app_logins"].mean().reindex(cid)
    feats = pd.DataFrame({
        "fuel": zscore(fuel_m.reset_index(drop=True)),
        "energy": zscore((e_ann + g_ann).reset_index(drop=True)),
        "elec": zscore(e_ann.reset_index(drop=True)),
        "hi": zscore(hi_spend.reset_index(drop=True)),
        "app": zscore(app.reset_index(drop=True)),
        "veh_age": zscore(veh["vehicle_age_years"].reset_index(drop=True)),
        "eco": zscore(hidden["eco_mindedness"]), "dig": zscore(hidden["digital_comfort"]),
        "inc": zscore(pd.Series(inc_num)),
        "loan": veh["has_vehicle_loan"].astype(float).reset_index(drop=True),
        "mort": (cust["tenure"] == "OWNER_MORTGAGE").astype(float).reset_index(drop=True),
        "outright": (cust["tenure"] == "OWNER_OUTRIGHT").astype(float).reset_index(drop=True),
    })
    base = {
        "GP01": 1.0 * feats.fuel + 0.9 * feats.eco + 0.5 * feats.inc + 0.4 * feats.veh_age + 0.3 * feats.loan,
        "GP02": 0.9 * feats.energy + 1.0 * feats.eco + 0.4 * feats.inc + 0.5 * feats.hi + 0.3 * feats.mort,
        "GP03": 1.0 * feats.eco + 1.1 * feats.elec + 0.5 * feats.inc + 0.4 * feats.outright,
        "GP04": 1.6 * feats.dig + 0.5 * feats.eco + 0.4 * feats.app,
    }
    idx = {c: i for i, c in enumerate(cid)}
    elig["_i"] = elig["customer_id"].map(idx)
    elig["took_up"] = np.nan
    elig["takeup_date"] = pd.NaT
    truth = []
    span = (OUTCOME_END - OUTCOME_START).days
    for pid in PRODUCTS:
        m = (elig.product_id == pid) & elig.eligible
        ii = elig.loc[m, "_i"].to_numpy()
        noise = rng.normal(0, 0.9, len(ii))
        b = base[pid].to_numpy()[ii] + noise
        b0 = solve_intercept(b, TARGET_PREVALENCE[pid])
        p = sigmoid(b + b0)
        y = (rng.random(len(ii)) < p).astype(int)
        elig.loc[m, "took_up"] = y
        days = rng.integers(0, span + 1, len(ii))
        elig.loc[m, "takeup_date"] = [(OUTCOME_START + pd.Timedelta(days=int(d))).date().isoformat() if yy else None
                                      for d, yy in zip(days, y)]
        truth.append(pd.DataFrame({"customer_id": elig.loc[m, "customer_id"].to_numpy(), "product_id": pid,
                                   "p_true": p.round(5)}))
    labels = elig.drop(columns="_i")
    labels["took_up"] = labels["took_up"].astype("Int64")
    return labels, pd.concat(truth, ignore_index=True), fuel_m


# ------------------------------------------------------------------ checks (the done-check)
def run_checks(cust, veh, tx, labels, fuel_m) -> dict:
    rep: dict = {}
    # 1. split is disjoint and ~70/15/15
    sizes = cust["split"].value_counts(normalize=True).round(3).to_dict()
    rep["split_fractions"] = sizes
    assert cust["customer_id"].is_unique
    # 2. no leakage in time
    assert pd.to_datetime(tx["date"]).max() <= CUTOFF, "transaction after cutoff"
    assert pd.to_datetime(tx["date"]).min() >= pd.Timestamp("2025-07-01"), "transaction before feature window"
    d = pd.to_datetime(labels["takeup_date"].dropna())
    assert ((d >= OUTCOME_START) & (d <= OUTCOME_END)).all(), "take-up outside outcome window"
    # 3. ineligible pairs have no label
    assert labels.loc[~labels.eligible, "took_up"].isna().all()
    assert labels.loc[labels.eligible, "took_up"].notna().all()
    # 4. prevalence and eligibility counts
    el = labels[labels.eligible]
    rep["prevalence_among_eligible"] = el.groupby("product_id")["took_up"].mean().round(3).to_dict()
    rep["eligible_counts"] = el.groupby("product_id").size().to_dict()
    rep["exclusion_counts"] = labels[~labels.eligible].groupby(["product_id", "exclusion_reason"]).size().rename(
        lambda x: x).reset_index(name="n").assign(k=lambda d: d.product_id + ":" + d.exclusion_reason).set_index("k")["n"].to_dict()
    # 5. DONE-CHECK: fuel spend correlates with EV take-up, but not perfectly
    ev = labels[(labels.product_id == "GP01") & labels.eligible].copy()
    ev["fuel_m"] = ev["customer_id"].map(fuel_m)
    y = ev["took_up"].astype(int).to_numpy()
    a = auc(ev["fuel_m"].to_numpy(), y)
    corr = float(np.corrcoef(ev["fuel_m"].to_numpy(), y)[0, 1])
    rep["ev_fuel_spend_auc"], rep["ev_fuel_spend_corr"] = round(a, 3), round(corr, 3)
    assert 0.55 < a < 0.90, f"fuel->EV AUC {a:.3f} outside (0.55, 0.90): too weak or too perfect"
    assert corr > 0.05
    # 6. descriptives
    rep["transactions"] = int(len(tx))
    rep["category_share"] = tx["category"].value_counts(normalize=True).round(3).to_dict()
    rep["missing_rates"] = {"annual_mileage_km": round(float(veh["annual_mileage_km"].isna().mean()), 3),
                            "vehicle_type_NONE": round(float((veh["vehicle_type"] == "NONE").mean()), 3)}
    return rep


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000, help="number of customers")
    ap.add_argument("--out", default="data")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()

    ss = np.random.SeedSequence(a.seed)
    r_cust, r_veh, r_en, r_dig, r_prod, r_tx, r_lab = [np.random.default_rng(s) for s in ss.spawn(7)]
    out = Path(a.out)
    (out / "_hidden").mkdir(parents=True, exist_ok=True)

    cust, hidden, inc_num = gen_customers(r_cust, a.n)
    veh = gen_vehicles(r_veh, cust, hidden, inc_num)
    energy = gen_energy(r_en, cust, hidden)
    digital = gen_digital(r_dig, cust, hidden)
    held = gen_products(r_prod, cust, veh, inc_num, hidden)
    tx = gen_transactions(r_tx, cust, hidden, veh, energy)
    labels, truth, fuel_m = gen_takeup(r_lab, cust, hidden, veh, inc_num, energy, tx, digital, held)
    rep = run_checks(cust, veh, tx, labels, fuel_m)
    rep.update({"seed": a.seed, "n_customers": a.n, "cutoff": str(CUTOFF.date())})

    cust.to_csv(out / "customers.csv", index=False)
    veh.to_csv(out / "vehicles.csv", index=False)
    energy.to_csv(out / "energy_monthly.csv", index=False)
    digital.to_csv(out / "digital_usage.csv", index=False)
    held.to_csv(out / "products_held.csv", index=False)
    tx.to_csv(out / "transactions.csv", index=False)
    labels.to_csv(out / "takeup_labels.csv", index=False)
    hidden.to_csv(out / "_hidden" / "traits.csv", index=False)
    truth.to_csv(out / "_hidden" / "true_takeup_probability.csv", index=False)
    pd.DataFrame([(c, t) for c, ts in TEMPLATES.items() for t in ts],
                 columns=["category", "template"]).to_csv(out / "merchant_templates.csv", index=False)
    (out / "generation_report.json").write_text(json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep, indent=2, default=str))
    print(f"\nOK - wrote {out}/ (checks passed)")


if __name__ == "__main__":
    main()
