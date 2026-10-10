"""GP04 Paperless. 4 pages x 5 g = 20 g per statement; paper 900 kg CO2e per tonne."""
import pytest
from src.engine.carbon import gp04_paperless


def test_monthly_statements(factors, assumptions):
    # 12 x 20 g = 240 g = 0.24 kg paper ; carbon 0.24/1000 x 900 = 0.216 kg (supplementary only)
    r = gp04_paperless(factors, assumptions, paper_statements_per_year=12)
    assert r.headline_metric == "kg_paper_avoided_per_yr"
    assert r.headline_value == pytest.approx(0.24)
    assert r.kg_co2e_avoided_per_yr is None
    assert r.supplementary["paper_production_carbon"]["kg_co2e_per_yr"] == pytest.approx(0.216)


def test_two_accounts(factors, assumptions):
    # 24 x 20 g = 0.48 kg ; 0.48/1000 x 900 = 0.432
    r = gp04_paperless(factors, assumptions, paper_statements_per_year=24)
    assert r.headline_value == pytest.approx(0.48)
    assert r.supplementary["paper_production_carbon"]["kg_co2e_per_yr"] == pytest.approx(0.432)


def test_paper_carbon_switched_off(factors, make_assumptions):
    # 52 x 20 g = 1.04 kg ; no supplementary carbon line, no paper factor ref
    a = make_assumptions(gp04_report_paper_carbon=False)
    r = gp04_paperless(factors, a, paper_statements_per_year=52)
    assert r.headline_value == pytest.approx(1.04)
    assert r.supplementary == {} and r.factor_refs == []


def test_already_paperless_not_applicable(factors, assumptions):
    r = gp04_paperless(factors, assumptions, paper_statements_per_year=0)
    assert r.status == "not_applicable"


def test_missing_statement_data_insufficient(factors, assumptions):
    r = gp04_paperless(factors, assumptions, paper_statements_per_year=None)
    assert r.status == "insufficient_data" and r.headline_value is None
