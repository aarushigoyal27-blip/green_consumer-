"""Deterministic carbon engine for PS1 products GP01-GP04.

Methodology: GHG Protocol project / avoided-emissions approach. For each product we
compare a baseline scenario (current behaviour) with a project scenario (after
adopting the product) over a one-year horizon:

    avoided = baseline_emissions - project_emissions

Rebound effects, embodied emissions (vehicle/panel manufacture) and well-to-tank
emissions are excluded. PCAF is not used: it covers financed-emissions accounting
for a lender's portfolio, which is not what is estimated here.

No ML, no eligibility decisions, no LLM. Inputs must already be annualised upstream
(features stage); None means "missing", 0 means "observed zero".
"""
from .factors import Assumptions, FactorTable
from .schema import ImpactResult

COMMON_ASSUMPTIONS = [
    "Annual horizon; baseline = current behaviour, project = after adopting the product",
    "Excludes rebound effects, embodied (manufacturing) emissions and well-to-tank emissions",
    "All figures are modelled estimates, not measured results",
]

EV_FUEL_TYPES = {"ev", "bev", "electric", "battery electric"}
ICE_FUEL_TYPES = {"petrol", "diesel"}


def _r(x, nd=3):
    return None if x is None else round(x, nd)


def _nonneg(**kw):
    for name, v in kw.items():
        if v is not None and v < 0:
            raise ValueError(f"{name} must be >= 0, got {v}")


def _carbon_result(product, status, baseline, project, **kw) -> ImpactResult:
    avoided = baseline - project
    return ImpactResult(
        product=product, status=status,
        headline_metric="kg_co2e_avoided_per_yr", headline_value=_r(avoided), headline_unit="kg CO2e/yr",
        kg_co2e_avoided_per_yr=_r(avoided),
        baseline_kg_co2e_per_yr=_r(baseline), project_kg_co2e_per_yr=_r(project), **kw)


# --------------------------------------------------------------------------- GP01
def gp01_ev_finance(factors: FactorTable, a: Assumptions, *, fuel_type,
                    annual_mileage_km=None, annual_fuel_spend_gbp=None) -> ImpactResult:
    P = "EV_FINANCE"
    _nonneg(annual_mileage_km=annual_mileage_km, annual_fuel_spend_gbp=annual_fuel_spend_gbp)
    ft = (fuel_type or "").strip().lower()
    if ft in EV_FUEL_TYPES:
        return ImpactResult(P, "not_applicable", method="Vehicle is already a battery EV; no avoided emissions from switching")

    assumptions = list(COMMON_ASSUMPTIONS)
    missing, quality = [], "high"
    if ft not in ICE_FUEL_TYPES:
        if not ft:
            missing.append("vehicle_fuel_type")
        else:
            assumptions.append(f"Fuel type '{fuel_type}' is not modelled separately")
        ft = a.value("gp01_unknown_fuel_default")
        assumptions.append(a.describe("gp01_unknown_fuel_default"))
        quality = "medium"

    ice_km = factors.get(f"{ft}_car_avg_km")
    bev_ef, bev_refs = factors.bev(a.value("electricity_include_td"))
    assumptions += [a.describe("electricity_include_td"),
                    "BEV per-km factor = average electric car kWh/km x 2026 UK electricity factor "
                    "(generation, plus T&D when included); see config/emission_factors.csv notes"]

    if annual_mileage_km is not None:
        km = annual_mileage_km
        baseline, project = km * ice_km.kg_co2e_per_unit, km * bev_ef
        return _carbon_result(
            P, "ok", baseline, project,
            breakdown={"annual_km": _r(km), "fuel_type_used": ft},
            estimate_quality=quality,
            method=f"annual_km x ({ft} car per-km factor - BEV per-km factor)",
            assumptions=assumptions, factor_refs=[ice_km.ref(), *bev_refs], missing_fields=missing)

    if annual_fuel_spend_gbp is not None:
        missing.append("annual_mileage_km")
        price_key = f"gp01_pump_price_{ft}"
        price = a.value(price_key)
        ice_l = factors.get(f"{ft}_litre")
        litres = annual_fuel_spend_gbp / price
        km_per_litre = ice_l.kg_co2e_per_unit / ice_km.kg_co2e_per_unit  # implied by DESNZ factors
        km_est = litres * km_per_litre
        baseline, project = litres * ice_l.kg_co2e_per_unit, km_est * bev_ef
        assumptions += [
            a.describe(price_key),
            "Mileage missing: litres = annual fuel spend / pump price; distance estimated as "
            "litres x (DESNZ per-litre factor / DESNZ per-km factor)",
            "Fuel spend assumed to be for this vehicle only",
        ]
        return _carbon_result(
            P, "ok", baseline, project,
            breakdown={"annual_fuel_spend_gbp": _r(annual_fuel_spend_gbp, 2), "litres_est": _r(litres),
                       "implied_km_per_litre": _r(km_per_litre), "annual_km_est": _r(km_est),
                       "fuel_type_used": ft},
            estimate_quality="low",
            method=f"fallback: litres x {ft} per-litre factor (baseline) - estimated km x BEV per-km factor (project)",
            assumptions=assumptions, factor_refs=[ice_l.ref(), ice_km.ref(), *bev_refs],
            missing_fields=missing)

    return ImpactResult(P, "insufficient_data", missing_fields=missing + ["annual_mileage_km", "annual_fuel_spend_gbp"],
                        method="Needs annual mileage or annual fuel spend; neither is available",
                        assumptions=assumptions)


# --------------------------------------------------------------------------- GP03
def gp03_solar_finance(factors: FactorTable, a: Assumptions, *, annual_electricity_kwh,
                       system_kwp=None) -> ImpactResult:
    P = "SOLAR_FINANCE"
    _nonneg(annual_electricity_kwh=annual_electricity_kwh, system_kwp=system_kwp)
    if annual_electricity_kwh is None:
        return ImpactResult(P, "insufficient_data", missing_fields=["annual_electricity_kwh"],
                            method="Needs annual electricity consumption to cap self-consumed generation")

    assumptions = list(COMMON_ASSUMPTIONS)
    if system_kwp is None:
        system_kwp = a.value("gp03_system_kwp")
        assumptions.append(a.describe("gp03_system_kwp"))
    else:
        assumptions.append(f"System size supplied for this customer: {system_kwp} kWp")
    yield_ = a.value("gp03_yield_kwh_per_kwp")
    include_td = a.value("electricity_include_td")
    ef, refs = factors.electricity(include_td)

    generation = system_kwp * yield_
    quality = "medium"
    if a.self_consumption_table is not None:
        archetype = a.value("gp03_occupancy_archetype")
        share, in_range, band = a.self_consumption_table.lookup(
            archetype, annual_electricity_kwh, generation)
        share_note = (f"Self-consumption share {share:.3f} from MCS MGD 003 look-up table (PV only), "
                      f"archetype '{archetype}', consumption band {band['c_min']}-{band['c_max']} kWh, "
                      f"generation band {band['g_min']}-{band['g_max']} kWh")
        if not in_range:
            quality = "low"
            share_note += ("; inputs outside MGD 003 validity (1,500-5,999 kWh use, <6,000 kWh "
                           "generation), nearest band used")
        share_assumptions = [a.describe("gp03_occupancy_archetype"), share_note]
    else:
        share = a.value("gp03_self_consumption_share")
        share_assumptions = [a.describe("gp03_self_consumption_share")]
    self_consumed = generation * share
    displaced = min(self_consumed, annual_electricity_kwh)
    capped = self_consumed > annual_electricity_kwh
    assumptions += [
        a.describe("gp03_yield_kwh_per_kwp"), *share_assumptions,
        a.describe("electricity_include_td"),
        "Only self-consumed generation is counted; exported generation is not credited",
        "Annual electricity use is annualised upstream from available months",
    ]
    if capped:
        assumptions.append("Self-consumed generation capped at the customer's annual electricity use")

    baseline = annual_electricity_kwh * ef
    project = (annual_electricity_kwh - displaced) * ef
    return _carbon_result(
        P, "ok", baseline, project,
        breakdown={"system_kwp": system_kwp, "generation_kwh": _r(generation),
                   "self_consumed_kwh": _r(self_consumed), "grid_kwh_displaced": _r(displaced),
                   "capped_at_consumption": capped, "electricity_factor_used": _r(ef, 5),
                   "self_consumption_share": _r(share, 4)},
        estimate_quality=quality,
        method="min(kWp x yield x self-consumption share (MCS MGD 003), annual electricity use) x grid electricity factor",
        assumptions=assumptions, factor_refs=refs)


# --------------------------------------------------------------------------- GP02
def gp02_green_home(factors: FactorTable, a: Assumptions, *, annual_electricity_kwh,
                    annual_gas_kwh) -> ImpactResult:
    P = "GREEN_HOME"
    _nonneg(annual_electricity_kwh=annual_electricity_kwh, annual_gas_kwh=annual_gas_kwh)
    if annual_electricity_kwh is None and annual_gas_kwh is None:
        return ImpactResult(P, "insufficient_data", missing_fields=["annual_electricity_kwh", "annual_gas_kwh"],
                            method="Needs electricity and/or gas consumption")

    assumptions = list(COMMON_ASSUMPTIONS) + [
        "Package = the GP02 catalogue use case (efficiency retrofits); one reduction share per fuel"]
    refs, missing, breakdown = [], [], {}
    baseline = project = 0.0

    if annual_electricity_kwh is not None:
        share = a.value("gp02_reduction_share_electricity")
        ef, erefs = factors.electricity(a.value("electricity_include_td"))
        saved = annual_electricity_kwh * share
        baseline += annual_electricity_kwh * ef
        project += (annual_electricity_kwh - saved) * ef
        breakdown["electricity"] = {"baseline_kwh": _r(annual_electricity_kwh), "kwh_saved": _r(saved),
                                    "kg_co2e_avoided": _r(saved * ef)}
        assumptions += [a.describe("gp02_reduction_share_electricity"), a.describe("electricity_include_td")]
        refs += erefs
    else:
        missing.append("annual_electricity_kwh")

    if annual_gas_kwh is not None:
        share = a.value("gp02_reduction_share_gas")
        gas = factors.get("natural_gas_gross_cv_kwh")
        saved = annual_gas_kwh * share
        baseline += annual_gas_kwh * gas.kg_co2e_per_unit
        project += (annual_gas_kwh - saved) * gas.kg_co2e_per_unit
        breakdown["gas"] = {"baseline_kwh": _r(annual_gas_kwh), "kwh_saved": _r(saved),
                            "kg_co2e_avoided": _r(saved * gas.kg_co2e_per_unit)}
        assumptions += [a.describe("gp02_reduction_share_gas"), "Gas kWh are gross calorific value, as on UK bills"]
        refs.append(gas.ref())
    else:
        missing.append("annual_gas_kwh")

    status = "partial" if missing else "ok"
    if missing:
        assumptions.append(f"Computed for available fuel only; not included: {', '.join(missing)}")
    return _carbon_result(
        P, status, baseline, project, breakdown=breakdown,
        estimate_quality="low" if missing else "medium",
        method="sum over fuels of annual kWh x assumed package reduction share x fuel factor",
        assumptions=assumptions, factor_refs=refs, missing_fields=missing)


# --------------------------------------------------------------------------- GP04
def gp04_paperless(factors: FactorTable, a: Assumptions, *, paper_statements_per_year) -> ImpactResult:
    P = "PAPERLESS_BANKING"
    _nonneg(paper_statements_per_year=paper_statements_per_year)
    if paper_statements_per_year is None:
        return ImpactResult(P, "insufficient_data", missing_fields=["paper_statements_per_year"],
                            method="Needs the number of paper statements received per year")
    if paper_statements_per_year == 0:
        return ImpactResult(P, "not_applicable", method="Customer already receives no paper statements")

    pages = a.value("gp04_pages_per_statement")
    gpp = a.value("gp04_grams_per_page")
    kg_paper = paper_statements_per_year * pages * gpp / 1000
    assumptions = [
        "Annual horizon; baseline = current paper statements, project = all statements digital",
        a.describe("gp04_pages_per_statement"), a.describe("gp04_grams_per_page"),
        "Envelopes, printing ink and postage logistics are excluded",
        "Digital adoption itself is never counted as a carbon reduction",
    ]
    result = ImpactResult(
        P, "ok", headline_metric="kg_paper_avoided_per_yr", headline_value=_r(kg_paper),
        headline_unit="kg paper/yr", kg_co2e_avoided_per_yr=None,
        breakdown={"paper_statements_per_year": paper_statements_per_year, "pages_avoided": paper_statements_per_year * pages},
        estimate_quality="medium",
        method="statements/yr x pages/statement x grams/page -> kg paper",
        assumptions=assumptions)

    if a.value("gp04_report_paper_carbon"):
        paper = factors.get("paper_primary_tonne")
        result.supplementary["paper_production_carbon"] = {
            "label": "Estimated emissions from producing the avoided paper (separate from headline metric)",
            "kg_co2e_per_yr": _r(kg_paper / 1000 * paper.kg_co2e_per_unit),
            "method": "kg paper / 1000 x DESNZ material-use factor (primary production, per tonne)",
        }
        result.factor_refs.append(paper.ref())
    return result


# --------------------------------------------------------------------------- dispatcher
# Keyed by opportunity name, NOT GP code: product numbering is decided at the output
# boundary (src/engine/recommend/opportunities.py), so a renumbering never touches carbon.
def compute_impact(opportunity: str, customer: dict, factors: FactorTable, a: Assumptions) -> dict:
    """Map a customer record (carbon-engine field names) to the right calculator. Returns a JSON-ready dict."""
    c = customer.get
    if opportunity == "EV_FINANCE":
        r = gp01_ev_finance(factors, a, fuel_type=c("vehicle_fuel_type"),
                            annual_mileage_km=c("annual_mileage_km"),
                            annual_fuel_spend_gbp=c("annual_fuel_spend_gbp"))
    elif opportunity == "GREEN_HOME":
        r = gp02_green_home(factors, a, annual_electricity_kwh=c("annual_electricity_kwh"),
                            annual_gas_kwh=c("annual_gas_kwh"))
    elif opportunity == "SOLAR_FINANCE":
        r = gp03_solar_finance(factors, a, annual_electricity_kwh=c("annual_electricity_kwh"),
                               system_kwp=c("solar_system_kwp"))
    elif opportunity == "PAPERLESS_BANKING":
        r = gp04_paperless(factors, a, paper_statements_per_year=c("paper_statements_per_year"))
    else:
        raise ValueError(f"unknown opportunity {opportunity!r}")
    return r.to_dict()
