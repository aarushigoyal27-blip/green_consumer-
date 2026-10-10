"""GP03 Solar. Electricity factor 0.20 + 0.02 T&D = 0.22. Default 4 kWp x 900 = 3,600 kWh,
x 0.5 self-consumption = 1,800 kWh."""
import pytest
from src.engine.carbon import gp03_solar_finance


def test_typical_home(factors, assumptions):
    # displaced 1,800 kWh x 0.22 = 396; baseline 4,000 x 0.22 = 880; project 2,200 x 0.22 = 484
    r = gp03_solar_finance(factors, assumptions, annual_electricity_kwh=4000)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(396)
    assert r.baseline_kg_co2e_per_yr == pytest.approx(880)
    assert r.project_kg_co2e_per_yr == pytest.approx(484)
    assert r.breakdown["capped_at_consumption"] is False


def test_capped_at_consumption(factors, assumptions):
    # self-consumed 1,800 > use 1,500 -> displaced 1,500 x 0.22 = 330
    r = gp03_solar_finance(factors, assumptions, annual_electricity_kwh=1500)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(330)
    assert r.breakdown["capped_at_consumption"] is True
    assert r.project_kg_co2e_per_yr == pytest.approx(0)


def test_no_energy_data_insufficient(factors, assumptions):
    r = gp03_solar_finance(factors, assumptions, annual_electricity_kwh=None)
    assert r.status == "insufficient_data" and r.kg_co2e_avoided_per_yr is None


def test_custom_system_size(factors, assumptions):
    # 3 kWp x 900 x 0.5 = 1,350 kWh x 0.22 = 297
    r = gp03_solar_finance(factors, assumptions, annual_electricity_kwh=5000, system_kwp=3.0)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(297)


def test_without_td_losses(factors, make_assumptions):
    # generation-only factor 0.20: 1,800 x 0.20 = 360; only one factor ref
    a = make_assumptions(electricity_include_td=False)
    r = gp03_solar_finance(factors, a, annual_electricity_kwh=4000)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(360)
    assert len(r.factor_refs) == 1


def test_zero_consumption_gives_zero(factors, assumptions):
    r = gp03_solar_finance(factors, assumptions, annual_electricity_kwh=0)
    assert r.status == "ok" and r.kg_co2e_avoided_per_yr == pytest.approx(0)
