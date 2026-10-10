"""Vocabulary guard tests for the exclusion engine. Run: pytest -q tests/test_exclusion_vocab.py"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import exclusion_engine as ee  # noqa: E402

CONTRACT = json.loads((ROOT / "config" / "contract.json").read_text())
INPUT = CONTRACT["schemas"]["customer_profile_input"]["properties"]

BASE = dict(CONTRACT["sample_payloads"]["sample_input_qualified_customer"])


def test_engine_vocabulary_matches_contract():
    for field, allowed in ee.VOCABULARY.items():
        contract_vals = {str(v).upper() for v in INPUT[field]["enum"] if v is not None}
        assert contract_vals == allowed, f"{field}: engine and contract.json disagree"


def test_frozen_account_is_excluded():
    d = ee.evaluate_customer_targeting({**BASE, "account_status": "FROZEN"}, "GP04")
    assert d["targeting_status"] == "EXCLUDED"
    assert "EXC_INACTIVE_ACCOUNT" in d["exclusion_reason_codes"]


@pytest.mark.parametrize("field,value", [("account_status", "SUSPENDED"),
                                          ("homeowner_status", "RENTING"),
                                          ("property_type", "HOUSEBOAT")])
def test_unknown_value_raises(field, value):
    with pytest.raises(ee.UnknownVocabularyError):
        ee.evaluate_customer_targeting({**BASE, field: value}, "GP02")


def test_validate_records_reports_all_problems_at_once():
    recs = [{**BASE, "account_status": "SUSPENDED"}, {**BASE, "account_status": "SUSPENDED"},
            {**BASE, "property_type": "HOUSEBOAT"}]
    with pytest.raises(ee.UnknownVocabularyError) as e:
        ee.validate_records(recs)
    assert e.value.problems == {"account_status": {"SUSPENDED": 2}, "property_type": {"HOUSEBOAT": 1}}


def test_missing_is_not_unknown():
    d = ee.evaluate_customer_targeting({**BASE, "homeowner_status": None}, "GP02")
    assert d["targeting_status"] == "INSUFFICIENT_DATA"
    d = ee.evaluate_customer_targeting({**BASE, "homeowner_status": "UNKNOWN"}, "GP02")
    assert d["targeting_status"] == "INSUFFICIENT_DATA"


def test_early_arrears_excludes_credit_products_only():
    c = {**BASE, "is_in_arrears": None, "delinquency_status": "30_DAYS"}
    assert "EXC_ARREARS_OR_DEFAULT" in ee.evaluate_customer_targeting(c, "GP01")["exclusion_reason_codes"]
    assert ee.evaluate_customer_targeting(c, "GP04")["targeting_status"] == "QUALIFIED"


def test_fuel_type_normalised_for_output():
    d = ee.evaluate_customer_targeting({**BASE, "vehicle_fuel_type": "ELECTRIC"}, "GP04")
    assert d["grounded_attributes"]["vehicle_fuel_type"] == "ev"
