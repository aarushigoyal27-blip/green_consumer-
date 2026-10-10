import pytest
from src.engine.recommend import StubExclusionAdapter

THRESHOLDS = {"EV_FINANCE": 0.5, "GREEN_HOME": 0.5, "SOLAR_FINANCE": 0.5, "PAPERLESS_BANKING": 0.5}


def full_customer(**overrides):
    c = {"customer_id": "C10001", "is_ev_owner": False, "has_ice_vehicle": True,
         "homeowner_status": "OWNER", "is_paperless": False,
         "vehicle_fuel_type": "petrol", "annual_mileage_km": 10_000,
         "baseline_electricity_kwh": 3000, "baseline_gas_kwh": 12000,
         "paper_statements_per_year": 12}
    c.update(overrides)
    return c


def props(cid="C10001", **p):
    """props(EV_FINANCE=0.9, ...) -> propensity dict; unspecified opportunities get 0.6."""
    base = {"EV_FINANCE": 0.6, "GREEN_HOME": 0.6, "SOLAR_FINANCE": 0.6, "PAPERLESS_BANKING": 0.6}
    base.update(p)
    return {(cid, o): {"propensity": v, "confidence": 0.8, "reason_codes": ["X"]} for o, v in base.items()}


@pytest.fixture
def run(factors, assumptions):
    def _run(customer, propensities=None, thresholds=THRESHOLDS, adapter=None):
        from src.engine.recommend import recommend_customer
        recs = recommend_customer(customer, propensities if propensities is not None else props(customer["customer_id"]),
                                  thresholds, adapter or StubExclusionAdapter(),
                                  factors, assumptions, "2026-06-30")
        return {r["opportunity"]: r for r in recs}
    return _run
