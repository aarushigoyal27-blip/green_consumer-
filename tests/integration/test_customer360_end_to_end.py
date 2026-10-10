"""End-to-end: data/customer_360.csv -> exclusion engine -> recommendation engine -> carbon engine.

Guards the seams between the independently-built components:
  * the data vocabulary is accepted by the (strict) exclusion engine,
  * take_up_GPxx label columns use the SAME numbering as contract.json (a past mix-up silently
    trained the EV model on green-home labels),
  * excluded customers never receive propensity or impact,
  * every non-excluded carbon opportunity gets an impact record from the carbon engine.
"""
from pathlib import Path

import pandas as pd
import pytest

import exclusion_engine as ee
from src.engine.carbon import load_assumptions, load_factors
from src.engine.recommend import (EngineExclusionAdapter, choose_thresholds, load_propensities,
                                  recommend_all, write_stub_propensities)
from src.engine.recommend.opportunities import OPPORTUNITY_TO_CODE

ROOT = Path(__file__).resolve().parents[2]
C360 = ROOT / "data" / "customer_360.csv"
pytestmark = pytest.mark.skipif(not C360.exists(), reason="data/customer_360.csv missing")

LABEL_TO_OPP = {"take_up_GP01": "EV_FINANCE", "take_up_GP02": "GREEN_HOME",
                "take_up_GP03": "SOLAR_FINANCE", "take_up_GP04": "PAPERLESS_BANKING"}


@pytest.fixture(scope="module")
def customers():
    df = pd.read_csv(C360)
    return df.astype(object).where(df.notna(), None).to_dict("records")


@pytest.fixture(scope="module")
def records(customers, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("stub") / "props.csv"
    write_stub_propensities([c["customer_id"] for c in customers], tmp)   # random stub, NOT a model
    props = load_propensities(tmp)
    thresholds = choose_thresholds([(o, v["propensity"]) for (_, o), v in props.items()], top_share=0.15)
    return recommend_all(customers, props, thresholds, EngineExclusionAdapter(),
                         load_factors(ROOT / "config/emission_factors.csv"),
                         load_assumptions(ROOT / "config/carbon_assumptions.yaml"), "2026-06-30")


def test_label_columns_follow_contract_numbering():
    cat = __import__("json").loads((ROOT / "config/contract.json").read_text())["product_catalogue"]
    assert {f"take_up_{code}": v["opportunity_key"] for code, v in cat.items()} == LABEL_TO_OPP
    assert {v: k for k, v in LABEL_TO_OPP.items()} == {o: f"take_up_{c}" for o, c in OPPORTUNITY_TO_CODE.items()}


def test_vocabulary_is_accepted_by_exclusion_engine(customers):
    assert ee.validate_records(customers) == len(customers)


def test_every_customer_gets_all_four_products(customers, records):
    assert len(records) == 4 * len(customers)
    assert {r["product_code"] for r in records} == {"GP01", "GP02", "GP03", "GP04"}


# Rules the synthetic label generator (scripts/data/step6) actually encodes per product.
# Other rules (opt-out, arrears, inactive account, property type, existing solar) were added to
# the data later and are NOT reflected in the labels -- see README "Known issues".
LABEL_LOGIC_CODES = {
    "EV_FINANCE": {"EXC_NO_VEHICLE", "EXC_ALREADY_EV_OWNER"},
    "GREEN_HOME": {"EXC_NOT_HOMEOWNER"},
    "SOLAR_FINANCE": {"EXC_NOT_HOMEOWNER"},
    "PAPERLESS_BANKING": {"EXC_ALREADY_PAPERLESS", "EXC_NO_DIGITAL_CHANNEL"},
}


@pytest.mark.parametrize("label,opp", LABEL_TO_OPP.items())
def test_label_numbering_matches_product_rules(label, opp, records, customers):
    """If take_up_GPxx drifts from contract numbering, positives hit the wrong product's rules
    (e.g. tenants 'taking up' Solar, or paperless customers 'taking up' Paperless)."""
    took = {c["customer_id"] for c in customers if c[label] is True}
    assert took, f"no positives for {label}"
    bad = [(r["customer_id"], r["exclusion_codes"]) for r in records
           if r["opportunity"] == opp and r["customer_id"] in took
           and LABEL_LOGIC_CODES[opp] & set(r["exclusion_codes"])]
    assert not bad, f"{label} positives violate {opp} product rules: {bad[:5]}"


def test_excluded_records_carry_no_propensity_or_impact(records):
    for r in (r for r in records if r["status"] == "excluded"):
        assert r["propensity"] is None and r["impact"] is None and r["exclusion_codes"]


def test_non_excluded_records_have_impact_from_carbon_engine(records):
    live = [r for r in records if r["status"] != "excluded"]
    assert live and all(r["impact"] is not None for r in live)
    assert any((r["impact"] or {}).get("status") == "ok" for r in live)
