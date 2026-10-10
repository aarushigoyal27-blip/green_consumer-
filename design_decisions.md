# Design Decisions – PS1 (Step 5)

> **Status: DRAFT for team sign-off (time-box 30 min).** Items marked ⚠ are the ones to argue about. Once agreed, freeze: after this, changes need all four owners to agree. Replace §5 with your frozen JSON contract if it differs.

## 1. Cutoff date and outcome window
| Item | Decision |
|---|---|
| Data cutoff (`data_as_of`) | `2026-06-30` |
| Feature window | Jan–Jun 2026 (6 months) – **all features computed only from data on or before the cutoff** |
| Outcome window | Jul–Dec 2026 – take-up labels measured **only** here |
| Impact horizon | Annual (kg CO₂e per year) |
| Split | Customer-level 70 / 15 / 15, seed 42, done *before* feature building |

⚠ **Seasonality:** 6 months of energy spend is not a typical year. Either (a) generate and use a 12-month lookback (Jul 2025–Jun 2026) for energy/fuel features, or (b) annualise with a documented seasonal factor. Recommended: **(a)**, keep outcome window Jul–Dec 2026.

## 2. Product catalogue
| ID | Product | Intended use case (what it finances) | Out of scope |
|---|---|---|---|
| GP01 | EV Finance | Replacing a petrol/diesel vehicle with an EV | Existing EV owners with no replacement need |
| GP02 | Green Home Loan | **Efficiency retrofits** that cut energy *demand*: insulation, glazing, heat pump, smart controls | Solar panels |
| GP03 | Solar Finance | **Generation**: solar panels (optionally with battery); home owners only | Efficiency retrofits |
| GP04 | Paperless Banking | Moving from paper to digital statements and journeys | Counted as carbon (never) |

- Mapping rule so GP02/GP03 never overlap: *reduces demand → Green Home; generates energy → Solar.*
- Optional products (Green Investments, Green Loans): **not attempted** (revisit only if time remains).

## 3. Exclusion rules (hard, applied after the model)
A propensity never establishes eligibility. These are **demo business rules**; real eligibility sits with the institution's authorised process, so output always carries `eligibility: "NOT_ASSESSED"`.

| Rule ID | Condition | Excluded product | Exclusion reason shown |
|---|---|---|---|
| EX01 | Owns an EV and no replacement use case | GP01 | `ALREADY_OWNS_EV` |
| EX02 | Not a home owner (renter / living with family) | GP02, GP03 | `NOT_HOME_OWNER` |
| EX03 | Already on paperless statements | GP04 | `ALREADY_PAPERLESS` |
| EX04 | Already holds the product | that product | `ALREADY_HOLDS_PRODUCT` |
| EX05 | Key input fields missing (e.g. no vehicle data for GP01) | that product | `INSUFFICIENT_DATA` |

- Excluded products are returned with `excluded: true` and a reason; **never** as recommendations.
- Ineligible customer × product pairs get **no take-up label** in the generator.
- ⚠ Define "replacement use case" for EX01 (suggested: second vehicle, or EV older than 8 years).

## 4. Reason codes (fixed list, 12)
| Code | Fires when (initial thresholds – tune on data) | Used for |
|---|---|---|
| `HIGH_FUEL_SPEND` | monthly fuel spend ≥ £150 | GP01 |
| `HIGH_ANNUAL_MILEAGE` | annual mileage ≥ 10,000 km | GP01 |
| `EXISTING_VEHICLE` | owns a petrol/diesel vehicle | GP01 |
| `OLDER_VEHICLE` | vehicle age ≥ 8 years | GP01 |
| `EXISTING_VEHICLE_LOAN` | active vehicle finance | GP01 |
| `HIGH_ELECTRICITY_SPEND` | monthly electricity spend in top quartile | GP02, GP03 |
| `HIGH_GAS_SPEND` | monthly gas spend in top quartile | GP02 |
| `HOME_OWNER` | owner-occupier or mortgage holder | GP02, GP03 |
| `HOME_IMPROVEMENT_SPEND` | recent home-improvement spend ≥ £X | GP02 |
| `PUBLIC_TRANSPORT_USE` | regular public-transport spend (eco-mindedness proxy) | GP01 (negative) / general |
| `PAPER_STATEMENTS` | paper-statement ratio ≥ 0.5 | GP04 |
| `HIGH_DIGITAL_ACTIVITY` | app/web logins above median | GP04 |

- Codes map from each customer's top-3 SHAP features (Step 9); each code states a direction (raises / lowers propensity).

## 5. JSON contract (draft – replace with frozen version)
```json
{
  "customer_id": "C10001",
  "opportunity": "EV_FINANCE",
  "product_id": "GP01",
  "propensity": 0.84,
  "confidence": 0.87,
  "reason_codes": ["HIGH_FUEL_SPEND", "HIGH_ANNUAL_MILEAGE", "EXISTING_VEHICLE"],
  "excluded": false,
  "exclusion_reason": null,
  "eligibility": "NOT_ASSESSED",
  "impact": {
    "value": 1850.0,
    "unit": "kg CO2e/year",
    "is_estimate": true,
    "method": "per-km factor difference (petrol vs EV)",
    "assumptions": ["annual_km=11200", "ef_petrol_per_km=…", "ef_ev_per_km=…"],
    "horizon": "annual"
  },
  "secondary_metrics": { "paper_saved_kg_per_year": null, "digital_adoption": null },
  "evidence": { "monthly_fuel_spend_gbp": 182.4, "annual_mileage_km": 11200, "vehicle_age_years": 9 },
  "data_timestamp": "2026-06-30",
  "model_version": "v0"
}
```
Excluded example: `{"customer_id":"C10002","opportunity":"EV_FINANCE","excluded":true,"exclusion_reason":"ALREADY_OWNS_EV","propensity":null,"impact":null,…}`

Rules: missing values are `null`, never guessed · the LLM may only use fields in this JSON · **Paperless impact** is reported as paper saved (kg/yr) under `secondary_metrics`; digital adoption is never carbon.

## 6. Open decisions (assign before leaving the meeting)
| # | Decision | Owner | Status |
|---|---|---|---|
| 1 | 12-month lookback vs annualise (§1) | | ☐ |
| 2 | "Replacement use case" definition (§3 EX01) | | ☐ |
| 3 | Recommendation threshold + max recommendations per customer | | ☐ |
| 4 | Emissions factors and sources (from Step 1 / `ASSUMPTIONS.md`) | | ☐ |
| 5 | Final JSON contract | | ☐ |
