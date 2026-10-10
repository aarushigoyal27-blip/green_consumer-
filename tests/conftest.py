"""Shared fixtures. Test factors (fixture CSV) are synthetic round numbers:
  elec generation 0.20 + T&D 0.02 = 0.22 kg/kWh | gas 0.18 kg/kWh
  petrol car 0.20 kg/km, 2.0 kg/litre (=> 10 km/l) | diesel car 0.16 kg/km, 2.4 kg/litre (=> 15 km/l)
  BEV 0.045 + T&D 0.005 = 0.05 kg/km | paper 900 kg/tonne
"""
from pathlib import Path

import pytest
import yaml

from src.engine.carbon import load_factors, load_assumptions
from src.engine.carbon.factors import Assumptions

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def factors():
    return load_factors(FIX / "test_factors.csv")


@pytest.fixture(scope="session")
def assumptions():
    return load_assumptions(FIX / "test_assumptions.yaml")


@pytest.fixture
def make_assumptions():
    """Build assumptions with overrides, e.g. make_assumptions(electricity_include_td=False)."""
    def _make(**overrides):
        data = yaml.safe_load((FIX / "test_assumptions.yaml").read_text())
        for k, v in overrides.items():
            data[k] = {"value": v, "source": "test override"}
        return Assumptions(data)
    return _make
