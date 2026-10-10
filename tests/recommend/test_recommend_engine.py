import pytest

from src.engine.recommend import (EngineExclusionAdapter, expected_impact_view, choose_thresholds,
                                  save_thresholds, load_thresholds, load_propensities,
                                  write_stub_propensities)
from src.engine.recommend import opportunities as opp_mod
from tests.recommend.conftest import full_customer, props


# ---- Step 11 done-checks ------------------------------------------------------------
def test_ev_only_customer_never_gets_ev_finance(run):
    r = run(full_customer(is_ev_owner=True, has_ice_vehicle=False), props(EV_FINANCE=0.99))
    assert r["EV_FINANCE"]["status"] == "excluded"
    assert r["EV_FINANCE"]["propensity"] is None and r["EV_FINANCE"]["impact"] is None
    assert r["EV_FINANCE"]["rank"] is None


def test_ev_owner_with_petrol_car_is_not_excluded(run):
    r = run(full_customer(is_ev_owner=True, has_ice_vehicle=True))
    assert r["EV_FINANCE"]["status"] == "recommended"


@pytest.mark.parametrize("tenure", ["TENANT", "LODGER", "COUNCIL_TENANT"])
def test_renter_never_gets_green_home_or_solar(run, tenure):
    r = run(full_customer(homeowner_status=tenure), props(GREEN_HOME=0.99, SOLAR_FINANCE=0.99))
    assert r["GREEN_HOME"]["status"] == r["SOLAR_FINANCE"]["status"] == "excluded"
    assert "EXC_NOT_HOMEOWNER" in r["SOLAR_FINANCE"]["exclusion_codes"]


def test_already_paperless_never_gets_paperless(run):
    r = run(full_customer(is_paperless=True), props(PAPERLESS_BANKING=0.99))
    assert r["PAPERLESS_BANKING"]["status"] == "excluded"


def test_unknown_tenure_is_insufficient_not_excluded(run):
    r = run(full_customer(homeowner_status=None))
    assert r["GREEN_HOME"]["status"] == "insufficient_data"
    assert r["GREEN_HOME"]["exclusion_codes"] == []
    assert "homeowner_status" in r["GREEN_HOME"]["missing_fields"]


# ---- threshold and ranking -----------------------------------------------------------
def test_threshold_boundary(run):
    r = run(full_customer(), props(EV_FINANCE=0.5, GREEN_HOME=0.4999))
    assert r["EV_FINANCE"]["status"] == "recommended"        # == threshold counts
    assert r["GREEN_HOME"]["status"] == "not_recommended"
    assert r["GREEN_HOME"]["propensity"] == 0.4999           # still reported, just not recommended


def test_ranked_by_propensity_desc(run):
    r = run(full_customer(), props(EV_FINANCE=0.7, GREEN_HOME=0.9, SOLAR_FINANCE=0.8, PAPERLESS_BANKING=0.1))
    assert (r["GREEN_HOME"]["rank"], r["SOLAR_FINANCE"]["rank"], r["EV_FINANCE"]["rank"]) == (1, 2, 3)
    assert r["PAPERLESS_BANKING"]["rank"] is None


def test_missing_propensity_is_insufficient(run):
    p = props()
    del p[("C10001", "SOLAR_FINANCE")]
    r = run(full_customer(), p)
    assert r["SOLAR_FINANCE"]["status"] == "insufficient_data"
    assert "propensity" in r["SOLAR_FINANCE"]["missing_fields"]


# ---- impact wiring -----------------------------------------------------------------
def test_impact_comes_from_carbon_engine(run):
    # fixture factors: petrol 0.20, BEV 0.05 km -> 10,000 km x 0.15 = 1,500
    r = run(full_customer())
    assert r["EV_FINANCE"]["impact"]["kg_co2e_avoided_per_yr"] == pytest.approx(1500)
    assert r["EV_FINANCE"]["impact"]["factor_refs"]
    # contract field names mapped: elec 3000 x 0.10 x 0.22 + gas 12000 x 0.20 x 0.18 = 66 + 432
    assert r["GREEN_HOME"]["impact"]["kg_co2e_avoided_per_yr"] == pytest.approx(498)


def test_input_carbon_number_is_ignored(run):
    r = run(full_customer(estimated_annual_reduction_kg=99999))
    assert r["EV_FINANCE"]["impact"]["kg_co2e_avoided_per_yr"] != 99999


def test_carbon_insufficient_does_not_block_recommendation(run):
    r = run(full_customer(annual_mileage_km=None))   # no mileage, no fuel spend
    assert r["EV_FINANCE"]["status"] == "recommended"
    assert r["EV_FINANCE"]["impact"]["status"] == "insufficient_data"


# ---- numbering isolation ---------------------------------------------------------------
def test_renumbering_changes_only_product_code(run, monkeypatch):
    before = run(full_customer())
    swapped = {"EV_FINANCE": "GP03", "GREEN_HOME": "GP01", "SOLAR_FINANCE": "GP02", "PAPERLESS_BANKING": "GP04"}
    monkeypatch.setattr(opp_mod, "OPPORTUNITY_TO_CODE", swapped)
    after = run(full_customer())
    for opp in before:
        b, a = dict(before[opp]), dict(after[opp])
        assert a["product_code"] == swapped[opp]
        b.pop("product_code"), a.pop("product_code")
        assert a == b


def test_default_numbering_matches_spec():
    assert opp_mod.OPPORTUNITY_TO_CODE == {"EV_FINANCE": "GP01", "GREEN_HOME": "GP02",
                                          "SOLAR_FINANCE": "GP03", "PAPERLESS_BANKING": "GP04"}


# ---- business view ---------------------------------------------------------------------
def test_expected_impact_view_separate_and_no_paper(run):
    recs = list(run(full_customer(), props(EV_FINANCE=0.8, GREEN_HOME=0.6)).values())
    snapshot = [dict(r) for r in recs]
    view = expected_impact_view(recs)
    assert recs == snapshot                                    # records untouched
    assert all(v["opportunity"] != "PAPERLESS_BANKING" for v in view)
    ev = next(v for v in view if v["opportunity"] == "EV_FINANCE")
    assert ev["expected_kg_co2e"] == pytest.approx(0.8 * 1500)  # 1,200


# ---- thresholds ------------------------------------------------------------------------
def test_threshold_is_kth_highest_on_validation():
    # 20 values 0.05..1.00; top 15% -> k = ceil(3.0) = 3 -> 3rd highest = 0.90
    rows = [("EV_FINANCE", round(0.05 * i, 2)) for i in range(1, 21)]
    assert choose_thresholds(rows, 0.15)["EV_FINANCE"] == pytest.approx(0.90)


def test_thresholds_must_come_from_validation(tmp_path):
    p = tmp_path / "t.json"
    save_thresholds({"EV_FINANCE": 0.9}, p, 0.15, split="test")
    with pytest.raises(ValueError):
        load_thresholds(p)


# ---- propensity file -------------------------------------------------------------------
def test_stub_propensity_roundtrip(tmp_path):
    p = tmp_path / "prop.csv"
    write_stub_propensities(["C1", "C2"], p)
    data = load_propensities(p)
    assert len(data) == 8 and all(0 <= v["propensity"] <= 1 for v in data.values())


def test_propensity_file_rejects_gp_codes(tmp_path):
    p = tmp_path / "prop.csv"
    p.write_text("customer_id,opportunity,propensity,confidence,reason_codes\nC1,GP01,0.5,0.8,\n")
    with pytest.raises(ValueError, match="opportunity"):
        load_propensities(p)


# ---- engine adapter (with a fake of the team's engine) ---------------------------------
def test_engine_adapter_maps_statuses():
    fake = lambda cust, opp: {"opportunity": opp, "targeting_status": "INSUFFICIENT_DATA",
                              "exclusion_reason_codes": [], "missing_fields": ["homeowner_status"]}
    r = EngineExclusionAdapter(fake)({"customer_id": "C1"}, "GREEN_HOME")
    assert r.status == "insufficient_data" and r.missing_fields == ["homeowner_status"]


def test_engine_adapter_catches_numbering_mismatch():
    fake = lambda cust, opp: {"opportunity": "GREEN_HOME", "targeting_status": "QUALIFIED",
                              "exclusion_reason_codes": []}
    with pytest.raises(ValueError, match="resolved"):
        EngineExclusionAdapter(fake)({"customer_id": "C1"}, "EV_FINANCE")
