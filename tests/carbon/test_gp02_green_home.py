"""GP02 Green Home. Electricity 0.22 kg/kWh, reduction 10%; gas 0.18 kg/kWh, reduction 20%."""
import pytest
from src.engine.carbon import gp02_green_home


def test_both_fuels(factors, assumptions):
    # elec 3,000 x 0.10 = 300 kWh x 0.22 = 66 ; gas 12,000 x 0.20 = 2,400 x 0.18 = 432 ; total 498
    r = gp02_green_home(factors, assumptions, annual_electricity_kwh=3000, annual_gas_kwh=12000)
    assert r.status == "ok"
    assert r.breakdown["electricity"]["kg_co2e_avoided"] == pytest.approx(66)
    assert r.breakdown["gas"]["kg_co2e_avoided"] == pytest.approx(432)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(498)


def test_spec_example_consumption(factors, assumptions):
    # 4,800 elec -> 480 x 0.22 = 105.6 ; 12,000 gas -> 432 ; total 537.6
    r = gp02_green_home(factors, assumptions, annual_electricity_kwh=4800, annual_gas_kwh=12000)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(537.6)


def test_missing_gas_is_partial(factors, assumptions):
    # electricity only: 66
    r = gp02_green_home(factors, assumptions, annual_electricity_kwh=3000, annual_gas_kwh=None)
    assert r.status == "partial"
    assert r.kg_co2e_avoided_per_yr == pytest.approx(66)
    assert "annual_gas_kwh" in r.missing_fields and "gas" not in r.breakdown


def test_missing_electricity_is_partial(factors, assumptions):
    # gas only: 10,000 x 0.20 = 2,000 x 0.18 = 360
    r = gp02_green_home(factors, assumptions, annual_electricity_kwh=None, annual_gas_kwh=10000)
    assert r.status == "partial" and r.kg_co2e_avoided_per_yr == pytest.approx(360)


def test_no_energy_insufficient(factors, assumptions):
    r = gp02_green_home(factors, assumptions, annual_electricity_kwh=None, annual_gas_kwh=None)
    assert r.status == "insufficient_data" and r.kg_co2e_avoided_per_yr is None


def test_all_electric_home_zero_gas_is_ok(factors, assumptions):
    # gas observed as 0 (not missing): status ok, total = electricity part 105.6
    r = gp02_green_home(factors, assumptions, annual_electricity_kwh=4800, annual_gas_kwh=0)
    assert r.status == "ok" and r.kg_co2e_avoided_per_yr == pytest.approx(105.6)
