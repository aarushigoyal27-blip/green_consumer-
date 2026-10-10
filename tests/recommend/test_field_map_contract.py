"""Every carbon input must come from a real contract field with a compatible unit."""
import json
from pathlib import Path

import pytest

from src.engine.recommend.field_map import CARBON_FIELD_MAP, to_carbon_inputs

CONTRACT = Path(__file__).parents[2] / "config" / "contract.json"
pytestmark = pytest.mark.skipif(not CONTRACT.exists(), reason="config/contract.json missing")


def _contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_every_mapped_source_field_exists_in_contract():
    props = _contract()["schemas"]["customer_profile_input"]["properties"]
    missing = [src for src in CARBON_FIELD_MAP.values() if src not in props]
    assert not missing, f"field_map points at fields not in contract.json: {missing}"


def test_mileage_is_km_in_contract():
    desc = _contract()["schemas"]["customer_profile_input"]["properties"]["annual_mileage_km"]["description"]
    assert "km" in desc.lower() or "kilomet" in desc.lower()


def test_contract_sample_maps_cleanly():
    sample = _contract()["sample_payloads"]["sample_input_qualified_customer"]
    inputs = to_carbon_inputs(sample)
    assert inputs["annual_mileage_km"] == 12000.0
    assert inputs["vehicle_fuel_type"] == "petrol"
    assert inputs["paper_statements_per_year"] == 12
