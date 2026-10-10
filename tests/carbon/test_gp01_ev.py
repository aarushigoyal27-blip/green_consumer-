"""GP01 EV Finance. Fixture factors: petrol 0.20 kg/km & 2.0 kg/l (10 km/l),
diesel 0.16 kg/km & 2.4 kg/l (15 km/l), BEV 0.05 kg/km. Pump: petrol £1.50, diesel £1.60."""
import pytest
from src.engine.carbon import gp01_ev_finance


def test_petrol_with_mileage(factors, assumptions):
    # 10,000 km x 0.20 = 2,000 baseline; 10,000 x 0.05 = 500 project; avoided 1,500
    r = gp01_ev_finance(factors, assumptions, fuel_type="petrol", annual_mileage_km=10_000)
    assert r.status == "ok" and r.estimate_quality == "high"
    assert r.baseline_kg_co2e_per_yr == pytest.approx(2000)
    assert r.project_kg_co2e_per_yr == pytest.approx(500)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(1500)


def test_diesel_with_mileage(factors, assumptions):
    # 20,000 x 0.16 = 3,200; 20,000 x 0.05 = 1,000; avoided 2,200
    r = gp01_ev_finance(factors, assumptions, fuel_type="Diesel", annual_mileage_km=20_000)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(2200)


def test_petrol_fallback_fuel_spend(factors, assumptions):
    # £1,200 / £1.50 = 800 l; baseline 800 x 2.0 = 1,600
    # km/l = 2.0/0.20 = 10 -> 8,000 km; project 8,000 x 0.05 = 400; avoided 1,200
    r = gp01_ev_finance(factors, assumptions, fuel_type="petrol", annual_fuel_spend_gbp=1200)
    assert r.status == "ok" and r.estimate_quality == "low"
    assert r.breakdown["litres_est"] == pytest.approx(800)
    assert r.breakdown["annual_km_est"] == pytest.approx(8000)
    assert r.baseline_kg_co2e_per_yr == pytest.approx(1600)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(1200)
    assert "annual_mileage_km" in r.missing_fields


def test_diesel_fallback_fuel_spend(factors, assumptions):
    # £960 / £1.60 = 600 l; baseline 600 x 2.4 = 1,440
    # km/l = 2.4/0.16 = 15 -> 9,000 km; project 450; avoided 990
    r = gp01_ev_finance(factors, assumptions, fuel_type="diesel", annual_fuel_spend_gbp=960)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(990)


def test_no_mileage_no_fuel_is_insufficient(factors, assumptions):
    r = gp01_ev_finance(factors, assumptions, fuel_type="petrol")
    assert r.status == "insufficient_data"
    assert r.kg_co2e_avoided_per_yr is None
    assert {"annual_mileage_km", "annual_fuel_spend_gbp"} <= set(r.missing_fields)


def test_ev_owner_not_applicable(factors, assumptions):
    r = gp01_ev_finance(factors, assumptions, fuel_type="EV", annual_mileage_km=12_000)
    assert r.status == "not_applicable" and r.kg_co2e_avoided_per_yr is None


def test_hybrid_defaults_to_petrol(factors, assumptions):
    # unmodelled fuel -> petrol default: 10,000 x (0.20 - 0.05) = 1,500, quality medium
    r = gp01_ev_finance(factors, assumptions, fuel_type="hybrid", annual_mileage_km=10_000)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(1500)
    assert r.estimate_quality == "medium"
    assert any("hybrid" in s for s in r.assumptions)


def test_missing_fuel_type_flagged(factors, assumptions):
    # 5,000 x 0.15 = 750
    r = gp01_ev_finance(factors, assumptions, fuel_type=None, annual_mileage_km=5_000)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(750)
    assert "vehicle_fuel_type" in r.missing_fields


def test_bev_factor_follows_td_switch(factors, make_assumptions):
    # generation only: BEV 0.045 ; 10,000 x (0.20 - 0.045) = 1,550 ; one BEV ref instead of two
    a = make_assumptions(electricity_include_td=False)
    r = gp01_ev_finance(factors, a, fuel_type="petrol", annual_mileage_km=10_000)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(1550)
    assert [f["activity"] for f in r.factor_refs] == ["petrol_car_avg_km", "bev_avg_km"]
