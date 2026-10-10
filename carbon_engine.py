"""Deterministic carbon engine for PS1 (rules and documented formulas only; no ML, no LLM).

Every factor is read from emission.csv (UK Government GHG Conversion Factors 2026, v1).
Every assumption that is NOT in that workbook is listed in ASSUMPTIONS below and is echoed
into the `assumptions` list of each impact record, so a reader can reproduce the number.

Method (all products): avoided emissions = baseline activity emissions - emissions after
the product is used, per year, using activity data x emission factor
(GHG Protocol project / avoided-emissions logic; operational emissions only, no well-to-tank).
Results are estimates, never guarantees.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent
FACTOR_FILE = ROOT / "emission.csv"

# Assumptions not contained in the GHG workbook. Source column says where each should be cited from.
ASSUMPTIONS: Dict[str, Dict[str, Any]] = {
    "solar_kwp_min": {"value": 2.0, "source": "Team assumption: smallest practical domestic array"},
    "solar_kwp_max": {"value": 6.0, "source": "Team assumption: typical roof and finance ceiling"},
    "solar_yield_kwh_per_kwp": {"value": 900.0, "source": "Team assumption: UK typical yield; confirm against MCS / PVGIS"},
    "solar_self_consumption": {"value": 0.5, "low": 0.4, "high": 0.7,
                               "source": "Team assumption: share of generation used on site without a battery"},
    "green_home_gas_reduction": {"value": 0.20, "low": 0.10, "high": 0.30,
                                 "source": "Team assumption: demand cut from insulation, glazing and controls"},
    "green_home_elec_reduction": {"value": 0.05, "low": 0.02, "high": 0.08,
                                  "source": "Team assumption: demand cut from smart controls and efficiency"},
    "paper_grams_per_statement": {"value": 10.0,
                                  "source": "Derived: two A4 sheets at 80 gsm (about 5 g each); envelope and postage excluded"},
    "petrol_price_gbp_per_litre": {"value": 1.45, "source": "Synthetic data price (generate_data.py PRICE)"},
    "diesel_price_gbp_per_litre": {"value": 1.52, "source": "Synthetic data price (generate_data.py PRICE)"},
    "litres_per_km": {"PETROL": 0.075, "DIESEL": 0.065, "HYBRID": 0.045,
                      "source": "Synthetic data consumption (generate_data.py LITRES_PER_KM); used only if mileage is missing"},
}

# emission.csv has no hybrid factor: hybrids return INSUFFICIENT_DATA rather than a guessed number
_CAR_ACTIVITY = {"PETROL": "Petrol car average", "DIESEL": "Diesel car average"}


def load_factors(path: Path = FACTOR_FILE) -> Dict[str, float]:
    df = pd.read_csv(path)
    return {f"{r.activity}|{r.unit}": float(r.kg_co2e_per_unit) for r in df.itertuples()}


FACTORS = load_factors()


def _f(activity: str, unit: str) -> float:
    return FACTORS[f"{activity}|{unit}"]


def _missing(x: Any) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _record(value: Optional[float], method: str, assumptions: list, basis: str, low=None, high=None,
            note: Optional[str] = None) -> Dict[str, Any]:
    return {
        "value": None if value is None else round(value, 1),
        "range_low": None if low is None else round(low, 1),
        "range_high": None if high is None else round(high, 1),
        "unit": "kg CO2e/year",
        "is_estimate": True,
        "method": method,
        "assumptions": assumptions,
        "horizon": "annual",
        "basis": basis,
        "note": note,
    }


def insufficient(note: str) -> Dict[str, Any]:
    return _record(None, "not computed", [], "INSUFFICIENT_DATA", note=note)


def ev_impact(inputs: Dict[str, Any]) -> Dict[str, Any]:
    vtype = inputs.get("vehicle_type")
    if vtype not in _CAR_ACTIVITY:
        return insufficient("No petrol, diesel or hybrid vehicle on record")
    km = inputs.get("annual_mileage_km")
    basis = "REPORTED_MILEAGE"
    if _missing(km):
        spend = inputs.get("annual_fuel_spend_gbp")
        if _missing(spend) or spend <= 0:
            return insufficient("Mileage and fuel spend both missing")
        price = ASSUMPTIONS["diesel_price_gbp_per_litre" if vtype == "DIESEL" else "petrol_price_gbp_per_litre"]["value"]
        km = spend / price / ASSUMPTIONS["litres_per_km"][vtype]
        basis = "FUEL_SPEND_ESTIMATE"
    base_f = _f(_CAR_ACTIVITY[vtype], "km")
    ev_f = _f("Battery EV average", "km")
    value = km * (base_f - ev_f)
    assumptions = [f"annual_km={round(km)}", f"ef_{vtype.lower()}_per_km={base_f}", f"ef_ev_per_km={ev_f}"]
    return _record(value, "per-km factor difference (current vehicle vs battery EV), UK Gov GHG factors 2026",
                   assumptions, basis)


def solar_impact(inputs: Dict[str, Any]) -> Dict[str, Any]:
    elec = inputs.get("annual_electricity_kwh")
    if _missing(elec) or elec <= 0:
        return insufficient("No electricity consumption on record")
    grid = _f("Grid electricity", "kWh") + _f("Electricity transmission and distribution losses", "kWh")
    yield_kwh = ASSUMPTIONS["solar_yield_kwh_per_kwp"]["value"]
    # array sized to match annual consumption, bounded to 2-6 kWp
    kwp = min(max(elec / yield_kwh, ASSUMPTIONS["solar_kwp_min"]["value"]), ASSUMPTIONS["solar_kwp_max"]["value"])
    system_kwh = kwp * yield_kwh
    sc = ASSUMPTIONS["solar_self_consumption"]

    def displaced(share):
        return min(system_kwh * share, elec)

    value = displaced(sc["value"]) * grid
    assumptions = [f"annual_electricity_kwh={round(elec)}", f"system_kwp={round(kwp, 2)}", f"system_kwh={round(system_kwh)}",
                   f"self_consumption={sc['value']}", f"ef_grid_incl_td_per_kwh={round(grid, 5)}"]
    return _record(value, "grid electricity displaced by on-site generation (generation + T&D factor)",
                   assumptions, "REPORTED_USAGE", low=displaced(sc["low"]) * grid, high=displaced(sc["high"]) * grid)


def green_home_impact(inputs: Dict[str, Any]) -> Dict[str, Any]:
    gas, elec = inputs.get("annual_gas_kwh"), inputs.get("annual_electricity_kwh")
    gas_ok = not _missing(gas) and gas > 0
    elec_ok = not _missing(elec) and elec > 0
    if not gas_ok and not elec_ok:
        return insufficient("No gas or electricity consumption on record")
    gas_f = _f("Natural gas", "kWh")
    el_f = _f("Grid electricity", "kWh") + _f("Electricity transmission and distribution losses", "kWh")
    g, e = ASSUMPTIONS["green_home_gas_reduction"], ASSUMPTIONS["green_home_elec_reduction"]

    def total(gr, er):
        return (gas * gr * gas_f if gas_ok else 0.0) + (elec * er * el_f if elec_ok else 0.0)

    assumptions = [f"annual_gas_kwh={round(gas) if gas_ok else 0}", f"annual_electricity_kwh={round(elec) if elec_ok else 0}",
                   f"gas_demand_reduction={g['value']}", f"electricity_demand_reduction={e['value']}",
                   f"ef_gas_per_kwh={gas_f}", f"ef_elec_incl_td_per_kwh={round(el_f, 5)}"]
    return _record(total(g["value"], e["value"]), "demand reduction x emission factor (gas gross CV, electricity incl. T&D)",
                   assumptions, "REPORTED_USAGE", low=total(g["low"], e["low"]), high=total(g["high"], e["high"]))


def paperless_impact(inputs: Dict[str, Any]) -> Dict[str, Any]:
    n = inputs.get("paper_statements_per_year")
    if _missing(n):
        return insufficient("No statement history on record")
    grams = ASSUMPTIONS["paper_grams_per_statement"]["value"]
    paper_kg = n * grams / 1000.0
    ef_t = _f("Paper (primary production)", "tonnes")
    value = paper_kg / 1000.0 * ef_t
    rec = _record(value, "paper production factor x paper no longer printed (postage excluded)",
                  [f"paper_statements_per_year={round(n)}", f"grams_per_statement={grams}", f"ef_paper_per_tonne={ef_t}"],
                  "REPORTED_USAGE")
    rec["secondary_metrics"] = {"paper_saved_kg_per_year": round(paper_kg, 2),
                                "paper_statements_per_year": round(n),
                                "digital_adoption": "separate from carbon; never converted to CO2e"}
    return rec


_DISPATCH = {"GP01": ev_impact, "GP02": green_home_impact, "GP03": solar_impact, "GP04": paperless_impact}


def compute_impact(product_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Return the impact record for GP01..GP04. Never guesses: missing inputs give value None."""
    return _DISPATCH[product_id](inputs)
