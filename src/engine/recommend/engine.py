"""Recommendation engine (Step 11).

Order of operations per customer x opportunity:
  1. Exclusions (adapter). Excluded -> never recommended; propensity withheld (contract: null if excluded).
  2. Propensity from the ML model (B). Missing -> insufficient_data.
  3. recommended  if propensity >= validation-chosen threshold, else not_recommended.
  4. Impact from the carbon engine for every non-excluded opportunity.
  5. Rank a customer's recommended products by propensity (ML output is never altered).

The business "expected impact" view (propensity x kg CO2e) is a SEPARATE function and
never changes status, rank or propensity.
"""
from src.engine.carbon import compute_impact

from .exclusion_adapter import ELIGIBLE, EXCLUDED, INSUFFICIENT
from .field_map import to_carbon_inputs
from .opportunities import CARBON_OPPORTUNITIES, OPPORTUNITIES, code_for

RECOMMENDED, NOT_RECOMMENDED, EXCLUDED_S, INSUFFICIENT_S = (
    "recommended", "not_recommended", "excluded", "insufficient_data")


def recommend_customer(customer, propensities, thresholds, exclusion_adapter,
                       factors, assumptions, data_as_of) -> list:
    cid = customer["customer_id"]
    carbon_inputs = to_carbon_inputs(customer)
    records = []
    for opp in OPPORTUNITIES:
        excl = exclusion_adapter(customer, opp)
        pred = propensities.get((cid, opp))
        rec = {
            "customer_id": cid, "opportunity": opp, "product_code": code_for(opp),
            "status": None, "rank": None,
            "propensity": None, "confidence": None, "reason_codes": [],
            "threshold": thresholds.get(opp),
            "exclusion_codes": excl.codes, "missing_fields": list(excl.missing_fields),
            "impact": None, "data_as_of": data_as_of,
        }
        if excl.status == EXCLUDED:
            rec["status"] = EXCLUDED_S
        elif excl.status == INSUFFICIENT:
            rec["status"] = INSUFFICIENT_S
        elif pred is None or rec["threshold"] is None:
            rec["status"] = INSUFFICIENT_S
            rec["missing_fields"].append("propensity" if pred is None else "threshold")
        else:
            rec.update(propensity=pred["propensity"], confidence=pred["confidence"],
                       reason_codes=pred["reason_codes"])
            rec["status"] = RECOMMENDED if pred["propensity"] >= rec["threshold"] else NOT_RECOMMENDED
        if rec["status"] != EXCLUDED_S:
            rec["impact"] = compute_impact(opp, carbon_inputs, factors, assumptions)
        records.append(rec)

    recommended = sorted((r for r in records if r["status"] == RECOMMENDED),
                         key=lambda r: (-r["propensity"], r["opportunity"]))
    for i, r in enumerate(recommended, start=1):
        r["rank"] = i
    return records


def recommend_all(customers, propensities, thresholds, exclusion_adapter,
                  factors, assumptions, data_as_of) -> list:
    out = []
    for c in customers:
        out.extend(recommend_customer(c, propensities, thresholds, exclusion_adapter,
                                      factors, assumptions, data_as_of))
    return out


def expected_impact_view(records) -> list:
    """Business view: recommended carbon products ranked by propensity x kg CO2e avoided.
    Paperless is excluded (its impact is kg paper, not CO2e). Does not modify records."""
    rows = []
    for r in records:
        if r["status"] != RECOMMENDED or r["opportunity"] not in CARBON_OPPORTUNITIES:
            continue
        kg = (r["impact"] or {}).get("kg_co2e_avoided_per_yr")
        if kg is None:
            continue
        rows.append({"customer_id": r["customer_id"], "opportunity": r["opportunity"],
                     "product_code": r["product_code"], "propensity": r["propensity"],
                     "kg_co2e_avoided_per_yr": kg,
                     "expected_kg_co2e": round(r["propensity"] * kg, 3)})
    return sorted(rows, key=lambda x: -x["expected_kg_co2e"])
