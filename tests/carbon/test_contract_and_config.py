"""Cross-cutting checks: output contract, config validation, real-CSV sanity."""
import csv
from pathlib import Path

import pytest

from src.engine.carbon import compute_impact, load_factors, ConfigError, gp01_ev_finance
from src.engine.carbon.factors import REQUIRED_ACTIVITIES

FIX = Path(__file__).parents[1] / "fixtures"
REAL_CSV = Path(__file__).parents[2] / "config" / "emission_factors.csv"

CUSTOMER = {"vehicle_fuel_type": "petrol", "annual_mileage_km": 12000,
            "annual_electricity_kwh": 3500, "annual_gas_kwh": 11000,
            "paper_statements_per_year": 12}


@pytest.mark.parametrize("product", ["EV_FINANCE", "GREEN_HOME",
                                     "SOLAR_FINANCE", "PAPERLESS_BANKING"])
def test_every_ok_result_is_traceable(product, factors, assumptions):
    r = compute_impact(product, CUSTOMER, factors, assumptions)
    assert r["status"] == "ok" and r["is_estimate"] is True
    assert r["method"] and r["assumptions"]
    if product != "PAPERLESS_BANKING" or r["supplementary"]:
        assert r["factor_refs"], "every carbon number must cite a factor"
    for ref in r["factor_refs"]:
        assert ref["source_sheet"] and ref["source_row_label"]


def test_digital_adoption_never_counted_as_carbon(factors, assumptions):
    r = compute_impact("PAPERLESS_BANKING", CUSTOMER, factors, assumptions)
    assert r["kg_co2e_avoided_per_yr"] is None


def test_negative_input_rejected(factors, assumptions):
    with pytest.raises(ValueError):
        gp01_ev_finance(factors, assumptions, fuel_type="petrol", annual_mileage_km=-5)


def _write(tmp_path, rows):
    p = tmp_path / "f.csv"
    with p.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["activity", "unit", "kg_co2e_per_unit", "scope", "factor_year",
                    "source_sheet", "source_row_label", "notes"])
        w.writerows(rows)
    return p


def _fixture_rows():
    with (FIX / "test_factors.csv").open() as fh:
        return [list(r.values()) for r in csv.DictReader(fh)]


def test_missing_activity_fails(tmp_path):
    rows = [r for r in _fixture_rows() if r[0] != "bev_avg_km"]
    with pytest.raises(ConfigError, match="bev_avg_km"):
        load_factors(_write(tmp_path, rows))


def test_per_mile_unit_fails(tmp_path):
    rows = [[*r[:1], "mile", *r[2:]] if r[0] == "petrol_car_avg_km" else r for r in _fixture_rows()]
    with pytest.raises(ConfigError, match="petrol_car_avg_km"):
        load_factors(_write(tmp_path, rows))


def test_duplicate_activity_fails(tmp_path):
    rows = _fixture_rows()
    with pytest.raises(ConfigError, match="duplicate"):
        load_factors(_write(tmp_path, rows + [rows[0]]))


# Rough plausibility ranges for UK DESNZ factors (sanity only; the CSV is the source of truth).
SANITY = {
    "electricity_generation_kwh": (0.10, 0.30),
    "natural_gas_gross_cv_kwh": (0.17, 0.20),
    "petrol_car_avg_km": (0.12, 0.25),
    "diesel_car_avg_km": (0.12, 0.25),
    "bev_avg_km": (0.02, 0.08),
    "petrol_litre": (1.9, 2.4),
    "diesel_litre": (2.3, 2.8),
}


@pytest.mark.skipif(not REAL_CSV.exists(), reason="config/emission_factors.csv not created yet")
def test_real_factors_load_and_are_plausible():
    t = load_factors(REAL_CSV)
    for act, (lo, hi) in SANITY.items():
        v = t.get(act).kg_co2e_per_unit
        assert lo <= v <= hi, f"{act}={v} outside {lo}-{hi}: wrong row or unit?"
    assert set(REQUIRED_ACTIVITIES) <= set(t._f)


@pytest.mark.skipif(not REAL_CSV.exists(), reason="config/emission_factors.csv not created yet")
def test_real_bev_factor_consistent_with_grid_factor():
    """BEV per-km ÷ grid per-kWh = implied kWh/km. Real BEVs (incl. charging losses) sit
    roughly 0.15-0.30 kWh/km. Outside that band usually means a per-mile row, a different
    factor year, or a different car size was copied."""
    t = load_factors(REAL_CSV)
    grid = (t.get("electricity_generation_kwh").kg_co2e_per_unit
            + t.get("electricity_td_kwh").kg_co2e_per_unit)
    bev = t.get("bev_avg_km").kg_co2e_per_unit + t.get("bev_td_avg_km").kg_co2e_per_unit
    implied = bev / grid
    assert 0.15 <= implied <= 0.30, (
        f"bev_avg_km implies {implied:.3f} kWh/km against the grid factor; check the DESNZ row "
        f"(per-mile vs per-km column, factor year, car size)")


@pytest.mark.skipif(not REAL_CSV.exists(), reason="config/emission_factors.csv not created yet")
def test_real_ice_factors_imply_plausible_fuel_economy():
    """per-km ÷ per-litre = litres/km. The GP01 fallback relies on this ratio."""
    t = load_factors(REAL_CSV)
    for fuel in ("petrol", "diesel"):
        l_per_100 = 100 * t.get(f"{fuel}_car_avg_km").kg_co2e_per_unit / t.get(f"{fuel}_litre").kg_co2e_per_unit
        assert 4.0 <= l_per_100 <= 12.0, f"{fuel}: implied {l_per_100:.1f} L/100km"
