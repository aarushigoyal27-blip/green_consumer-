"""GP03 with the MCS MGD 003 self-consumption look-up (real table, synthetic factors).
Fixture: electricity 0.20 + 0.02 T&D = 0.22 kg/kWh; default 4 kWp x 900 = 3,600 kWh generated.
Shares below are read from config/mcs_mgd003_pv_only.csv (PV only)."""
from pathlib import Path

import pytest
import yaml

from src.engine.carbon import gp03_solar_finance, ConfigError
from src.engine.carbon.factors import Assumptions, load_self_consumption_table, load_assumptions

ROOT = Path(__file__).parents[2]
TABLE = ROOT / "config" / "mcs_mgd003_pv_only.csv"
FIX = Path(__file__).parents[1] / "fixtures"


@pytest.fixture(scope="module")
def table():
    return load_self_consumption_table(TABLE)


def _assumptions(table, archetype="In half the day"):
    data = yaml.safe_load((FIX / "test_assumptions.yaml").read_text())
    data.pop("gp03_self_consumption_share")
    data["gp03_occupancy_archetype"] = {"value": archetype, "source": "test"}
    return Assumptions(data, table)


def test_typical_home_in_half_the_day(factors, table):
    # band 3500-3999 kWh use, 3600-3899 kWh gen -> 0.241428 ; 3600 x 0.241428 = 869.141 kWh x 0.22 = 191.211
    r = gp03_solar_finance(factors, _assumptions(table), annual_electricity_kwh=3500)
    assert r.breakdown["self_consumption_share"] == pytest.approx(0.2414, abs=1e-4)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(191.211, abs=1e-3)
    assert r.estimate_quality == "medium"
    assert any("MGD 003" in s for s in r.assumptions)


def test_home_all_day_uses_more_on_site(factors, table):
    # 0.304041 ; 3600 x 0.304041 = 1094.548 kWh x 0.22 = 240.801
    r = gp03_solar_finance(factors, _assumptions(table, "Home all day"), annual_electricity_kwh=3500)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(240.801, abs=1e-3)


def test_smaller_system_different_generation_band(factors, table):
    # 3 kWp x 900 = 2700 kWh -> band 2700-2999 -> 0.285648 (see CSV) ; 2700 x share x 0.22
    share = table.lookup("In half the day", 3500, 2700)[0]
    r = gp03_solar_finance(factors, _assumptions(table), annual_electricity_kwh=3500, system_kwp=3.0)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(2700 * share * 0.22, abs=1e-3)


def test_low_use_outside_mgd003_range_is_flagged(factors, table):
    # 1000 kWh < 1500: nearest band 1500-1999 -> 0.141131 ; 3600 x 0.141131 = 508.072 kWh x 0.22 = 111.776
    r = gp03_solar_finance(factors, _assumptions(table), annual_electricity_kwh=1000)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(111.776, abs=1e-3)
    assert r.estimate_quality == "low"
    assert any("outside MGD 003 validity" in s for s in r.assumptions)


def test_high_use_outside_range_uses_top_band(factors, table):
    # 8000 kWh >= 6000: band 5500-5999 -> 0.318607 ; 3600 x 0.318607 = 1146.985 x 0.22 = 252.337
    r = gp03_solar_finance(factors, _assumptions(table), annual_electricity_kwh=8000)
    assert r.kg_co2e_avoided_per_yr == pytest.approx(252.337, abs=1e-3)
    assert r.estimate_quality == "low"


def test_band_edges_are_contiguous(table):
    assert table.lookup("In half the day", 3499.9, 3599.9)[2]["c_min"] == 3000
    assert table.lookup("In half the day", 3500, 3600)[2]["g_min"] == 3600


def test_unknown_archetype_rejected(table):
    with pytest.raises(ConfigError, match="archetype"):
        table.lookup("Night shift", 3000, 3000)


def test_production_config_uses_mgd003():
    a = load_assumptions(ROOT / "config" / "carbon_assumptions.yaml")
    assert a.self_consumption_table is not None
    assert a.value("gp03_occupancy_archetype") == "In half the day"


def test_mgd003_method_requires_archetype(tmp_path):
    data = yaml.safe_load((FIX / "test_assumptions.yaml").read_text())
    data["gp03_self_consumption_method"] = {"value": "mcs_mgd003", "source": "t"}
    p = tmp_path / "a.yaml"
    p.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigError, match="gp03_occupancy_archetype"):
        load_assumptions(p)
