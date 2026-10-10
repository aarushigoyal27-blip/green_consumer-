"""Acceptance tests for the exclusion engine fixes ("definition of done").

Written BEFORE the fix. Run:  pytest tests/acceptance -v
Expected today: many failures. Expected after the fix: all pass.

NAMES THIS FILE ASSUMES (team decision "Option A"). If the team picks different
names, edit ONLY this block, not the tests.
"""
import json
from pathlib import Path

import pytest

ee = pytest.importorskip("exclusion_engine")
evaluate = ee.evaluate_customer_targeting

# ---------------------------------------------------------------- assumed names
SPEC_CODES = {"EV_FINANCE": "GP01", "GREEN_HOME": "GP02", "SOLAR_FINANCE": "GP03",
              "PAPERLESS_BANKING": "GP04"}                       # Lloyds PS1 Section 2
QUALIFIED, EXCLUDED, INSUFFICIENT = "QUALIFIED", "EXCLUDED", "INSUFFICIENT_DATA"
EXC_NOT_HOMEOWNER = "EXC_NOT_HOMEOWNER"
EXC_ALREADY_EV = "EXC_ALREADY_EV_OWNER"
EXC_ALREADY_PAPERLESS = "EXC_ALREADY_PAPERLESS"
EXC_MAX_EFFICIENCY = "EXC_PROPERTY_MAX_EFFICIENCY"               # new in Option A
EXC_PROPERTY_TYPE = "EXC_PROPERTY_TYPE_INELIGIBLE"               # new in Option A
EXC_SOLAR_INSTALLED = "EXC_ALREADY_SOLAR_INSTALLED"              # new in Option A
EXC_NO_VEHICLE = "EXC_NO_VEHICLE"                                # new in Option A
EXC_NO_DIGITAL = "EXC_NO_DIGITAL_CHANNEL"                        # new in Option A
EXC_MISSING_DATA = "EXC_MISSING_DATA"
EXC_DUPLICATE = "EXC_DUPLICATE_OFFER"
EXC_REGIONAL = "EXC_REGIONAL_RESTRICTION"
EXC_CREDIT = "EXC_LOW_CREDIT_SCORE"
NEW_INPUT_FIELD_ICE = "has_ice_vehicle"                          # new contract field (FR7)
# ------------------------------------------------------------------------------

BASE = {  # fully qualified for all four products
    "customer_id": "C10001", "homeowner_status": "OWNER", "is_ev_owner": False,
    NEW_INPUT_FIELD_ICE: True, "is_paperless": False, "has_vehicle": True, "has_solar": False,
    "has_digital_banking": True, "digital_logins_90d": 18, "property_type": "SEMI_DETACHED",
    "property_epc_rating": "E", "is_in_arrears": False, "delinquency_status": "CURRENT",
    "age": 42, "marketing_consent": True, "account_status": "ACTIVE",
    "transaction_count_6m": 240, "uk_resident": True, "country_code": "GB",
    "compliance_status": "CLEAR", "days_since_last_offer_decline": None,
    "annual_fuel_spend": 2400.0, "baseline_electricity_kwh": 4800.0,
    "baseline_gas_kwh": 12000.0, "data_cutoff_date": "2026-06-30",
}


def run(opportunity, **overrides):
    profile = {**BASE, **overrides}
    return evaluate(profile, SPEC_CODES[opportunity])


def drop(opportunity, *fields):
    profile = {k: v for k, v in BASE.items() if k not in fields}
    return evaluate(profile, SPEC_CODES[opportunity])


# 1 --------------------------------------------------------------- numbering
@pytest.mark.parametrize("opportunity,code", SPEC_CODES.items())
def test_spec_code_resolves_to_spec_product(opportunity, code):
    out = evaluate(dict(BASE), code)
    assert out["opportunity"] == opportunity
    assert out["product_code"] == code


@pytest.mark.parametrize("opportunity", SPEC_CODES)
def test_base_profile_qualifies(opportunity):
    out = run(opportunity)
    assert out["targeting_status"] == QUALIFIED, out["exclusion_reason_codes"]


# 2 ------------------------------------------------------- must-have rules (Step 5c)
def test_ev_only_owner_excluded_from_ev():
    out = run("EV_FINANCE", is_ev_owner=True, **{NEW_INPUT_FIELD_ICE: False})
    assert out["targeting_status"] == EXCLUDED and EXC_ALREADY_EV in out["exclusion_reason_codes"]


def test_ev_owner_with_ice_car_not_excluded():          # FR7: replacement use case exists
    out = run("EV_FINANCE", is_ev_owner=True, **{NEW_INPUT_FIELD_ICE: True})
    assert EXC_ALREADY_EV not in out["exclusion_reason_codes"]


@pytest.mark.parametrize("opportunity", ["GREEN_HOME", "SOLAR_FINANCE"])
@pytest.mark.parametrize("tenure", ["TENANT", "LODGER", "COUNCIL_TENANT"])
def test_renter_excluded_from_home_products(opportunity, tenure):
    out = run(opportunity, homeowner_status=tenure)
    assert out["targeting_status"] == EXCLUDED and EXC_NOT_HOMEOWNER in out["exclusion_reason_codes"]


def test_already_paperless_excluded():
    out = run("PAPERLESS_BANKING", is_paperless=True)
    assert EXC_ALREADY_PAPERLESS in out["exclusion_reason_codes"]


# 3 ------------------------------------------------------- correct labels (Option A)
@pytest.mark.parametrize("opportunity,overrides,code", [
    ("GREEN_HOME", {"property_epc_rating": "A"}, EXC_MAX_EFFICIENCY),
    ("GREEN_HOME", {"property_epc_rating": "B"}, EXC_MAX_EFFICIENCY),
    ("SOLAR_FINANCE", {"property_type": "FLAT"}, EXC_PROPERTY_TYPE),
    ("SOLAR_FINANCE", {"has_solar": True}, EXC_SOLAR_INSTALLED),
    ("EV_FINANCE", {"has_vehicle": False, "annual_fuel_spend": 0.0}, EXC_NO_VEHICLE),
    ("PAPERLESS_BANKING", {"has_digital_banking": False}, EXC_NO_DIGITAL),
])
def test_exclusion_has_truthful_code(opportunity, overrides, code):
    out = run(opportunity, **overrides)
    assert out["targeting_status"] == EXCLUDED
    assert code in out["exclusion_reason_codes"]
    assert EXC_MISSING_DATA not in out["exclusion_reason_codes"]     # nothing is missing here
    assert "EXC_INACTIVE_ACCOUNT" not in out["exclusion_reason_codes"]  # account is active


# 4 ------------------------------------------------------- missing data != exclusion
@pytest.mark.parametrize("opportunity", ["GREEN_HOME", "SOLAR_FINANCE"])
def test_missing_tenure_is_insufficient_not_renter(opportunity):
    out = drop(opportunity, "homeowner_status")
    assert out["targeting_status"] == INSUFFICIENT
    assert EXC_NOT_HOMEOWNER not in out["exclusion_reason_codes"]


@pytest.mark.parametrize("opportunity", ["GREEN_HOME", "SOLAR_FINANCE"])
def test_unknown_tenure_is_insufficient_not_renter(opportunity):
    out = run(opportunity, homeowner_status="UNKNOWN")
    assert out["targeting_status"] == INSUFFICIENT


def test_fuel_spend_missing_but_mileage_known_not_excluded():
    p = {k: v for k, v in BASE.items() if k != "annual_fuel_spend"}
    p["annual_mileage_km"] = 12000
    out = evaluate(p, SPEC_CODES["EV_FINANCE"])
    assert out["targeting_status"] != EXCLUDED, out["exclusion_reason_codes"]


@pytest.mark.parametrize("field", ["annual_fuel_spend", "digital_logins_90d", "country_code",
                                   "compliance_status", "account_status", "age"])
@pytest.mark.parametrize("opportunity", SPEC_CODES)
def test_null_values_never_crash_or_exclude_by_accident(field, opportunity):
    out = run(opportunity, **{field: None})
    assert out["targeting_status"] in (QUALIFIED, INSUFFICIENT), (field, out["exclusion_reason_codes"])


@pytest.mark.parametrize("opportunity", SPEC_CODES)
def test_empty_profile_does_not_crash(opportunity):
    out = evaluate({"customer_id": "C99999"}, SPEC_CODES[opportunity])
    assert out["targeting_status"] in (EXCLUDED, INSUFFICIENT)
    assert EXC_NOT_HOMEOWNER not in out["exclusion_reason_codes"]


# 5 ------------------------------------------------------- specific bugs found in review
@pytest.mark.parametrize("days,excluded", [(0, True), (89, True), (90, False)])
def test_cooling_off_boundaries(days, excluded):
    out = run("GREEN_HOME", days_since_last_offer_decline=days)
    assert (EXC_DUPLICATE in out["exclusion_reason_codes"]) is excluded


def test_null_country_code_not_regional_restriction():
    out = run("GREEN_HOME", country_code=None)
    assert EXC_REGIONAL not in out["exclusion_reason_codes"]


# 6 ------------------------------------------------------- responsible AI (team policy)
def test_vulnerable_customer_not_auto_excluded():
    # Contract v2.1.0: vulnerability is read ONLY from vulnerability_flag (not delinquency_status).
    out = run("GREEN_HOME", vulnerability_flag=True)
    assert out["targeting_status"] == QUALIFIED               # Consumer Duty: extra care, not exclusion
    assert out["requires_human_review"] is True


def test_unknown_delinquency_value_is_rejected_not_ignored():
    # v2.1.0: unknown categorical values raise instead of passing silently.
    with pytest.raises(ee.UnknownVocabularyError):
        run("GREEN_HOME", delinquency_status="VULNERABLE")


def test_no_upper_age_cutoff():
    out = run("GREEN_HOME", age=86)
    assert out["targeting_status"] == QUALIFIED


def test_arrears_still_excluded_from_credit_products():
    out = run("GREEN_HOME", is_in_arrears=True)
    assert out["targeting_status"] == EXCLUDED


def test_arrears_does_not_block_paperless():
    out = run("PAPERLESS_BANKING", is_in_arrears=True)
    assert out["targeting_status"] == QUALIFIED


# 7 ------------------------------------------------------- separation of duties
def test_engine_does_not_echo_input_carbon_numbers():
    out = run("EV_FINANCE", estimated_annual_reduction_kg=99999)
    assert "99999" not in json.dumps(out)        # carbon comes from the carbon engine only


def test_excluded_has_null_propensity():
    out = run("PAPERLESS_BANKING", is_paperless=True)
    assert out["propensity"] is None and out["confidence"] is None


# 8 ------------------------------------------------------- contract conformance
def _contract():
    path = Path(ee.__file__).parent / "config" / "contract.json"
    if not path.exists():
        pytest.skip("config/contract.json not found")
    return json.loads(path.read_text(encoding="utf-8"))


def test_contract_numbering_matches_spec():
    cat = _contract()["product_catalogue"]
    assert {code: v["opportunity_key"] for code, v in cat.items()} == \
           {v: k for k, v in SPEC_CODES.items()}


def test_contract_has_no_embedded_emission_factors():
    text = json.dumps(_contract()["product_catalogue"])
    assert "kg_co2e_per" not in text, "factors live in config/emission_factors.csv only"


def test_contract_allows_insufficient_status():
    out_schema = _contract()["schemas"]["single_product_decision_output"]
    assert INSUFFICIENT in out_schema["properties"]["targeting_status"]["enum"]


@pytest.mark.parametrize("opportunity", SPEC_CODES)
@pytest.mark.parametrize("overrides", [{}, {"is_paperless": True, "homeowner_status": "TENANT",
                                            "is_ev_owner": True, NEW_INPUT_FIELD_ICE: False}])
def test_output_validates_against_contract(opportunity, overrides):
    jsonschema = pytest.importorskip("jsonschema")
    contract = _contract()
    schema = {**contract["schemas"]["single_product_decision_output"], "schemas": contract["schemas"]}
    jsonschema.validate(run(opportunity, **overrides), schema)
