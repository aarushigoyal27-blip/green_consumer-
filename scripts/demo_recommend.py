"""End-to-end smoke run: real DESNZ factors + stub exclusions + stub propensities.
Usage: python scripts/demo_recommend.py [--engine]   (--engine uses the team's exclusion_engine.py)
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engine.carbon import load_factors, load_assumptions
from src.engine.recommend import (StubExclusionAdapter, EngineExclusionAdapter, recommend_all,
                                  expected_impact_view, write_stub_propensities, load_propensities,
                                  choose_thresholds)

_root = Path(__file__).resolve().parents[1]
_SAMPLE = json.loads((_root / "config/contract.json").read_text(encoding="utf-8"))[
    "sample_payloads"]["sample_input_qualified_customer"]   # full contract profile, C10001

CUSTOMERS = [
    dict(_SAMPLE),
    # C10042 / C10077 are deliberately partial profiles: with --engine they show INSUFFICIENT_DATA
    {"customer_id": "C10042", "is_ev_owner": True, "has_ice_vehicle": False, "homeowner_status": "TENANT",
     "is_paperless": True, "baseline_electricity_kwh": 4200},
    {"customer_id": "C10077", "is_ev_owner": False, "has_ice_vehicle": True, "homeowner_status": None,
     "is_paperless": False, "vehicle_fuel_type": "diesel", "annual_fuel_spend": 1800,
     "baseline_electricity_kwh": None, "baseline_gas_kwh": None, "paper_statements_per_year": 24},
]

root = Path(__file__).resolve().parents[1]
factors = load_factors(root / "config/emission_factors.csv")
assumptions = load_assumptions(root / "config/carbon_assumptions.yaml")
stub = root / "data/stub/propensities_stub.csv"
stub.parent.mkdir(parents=True, exist_ok=True)
write_stub_propensities([c["customer_id"] for c in CUSTOMERS], stub)
props = load_propensities(stub)
# DEMO ONLY: real thresholds must come from B's validation split via choose_thresholds().
thresholds = choose_thresholds([(o, v["propensity"]) for (_, o), v in props.items()], top_share=0.5)
adapter = EngineExclusionAdapter() if "--engine" in sys.argv else StubExclusionAdapter()

records = recommend_all(CUSTOMERS, props, thresholds, adapter, factors, assumptions, "2026-06-30")
for r in records:
    imp = r["impact"] or {}
    print(f'{r["customer_id"]} {r["product_code"]} {r["opportunity"]:17s} {r["status"]:16s} '
          f'rank={r["rank"]} p={r["propensity"]} codes={r["exclusion_codes"]} '
          f'impact={imp.get("headline_value")} {imp.get("headline_unit") or ""} [{imp.get("status","-")}]')
print("\nBusiness view (propensity x kg CO2e):")
print(json.dumps(expected_impact_view(records), indent=1))
