> ⚠️ **SUPERSEDED IN PART — read before relying on this document.**
> This is the v1.0 design spec. The **frozen contract is `config/contract.json` v2.1.0** and
> `exclusion_engine.py` implements it. Where they differ, the contract wins. Known differences:
> - **Product numbering:** GP01 = EV Finance, GP02 = Green Home, GP03 = Solar, GP04 = Paperless
>   (this document's tables use GP01 = Green Home, GP02 = Solar, GP03 = EV).
> - **Reason codes:** the contract defines its own list (e.g. `EXC_OPT_OUT`, `EXC_ARREARS_OR_DEFAULT`,
>   `EXC_NO_VEHICLE`, `EXC_INACTIVE_ACCOUNT`), not the "12 immutable codes" below.
> - **Outputs:** `targetable` replaces `is_eligible`; a third status `INSUFFICIENT_DATA` exists
>   (missing data is never treated as a negative fact).
> The cutoff date, feature window and outcome window below are still correct.

# Product Targeting & Exclusion Pipeline: Core Design Decisions
**Megathon X: Singularity — Problem Statement 1 (Green Customer Insights Platform)**  
*Document Version: 1.0 (Frozen Architecture Specification)*  
*Status: Approved & Frozen for Downstream Implementation*

---

## 1. Executive Summary & Architecture Context

This document establishes and freezes the core architecture, temporal boundaries, product catalogue taxonomy, business exclusion rules, and reason codes for the **Product Targeting and Exclusion Pipeline**.

As mandated by the Megathon core architectural governance ("*Every component has exactly one job*"):
- **Eligibility & Exclusion Engine**: Deterministically enforces authorized business logic, consumer protection constraints, and regulatory rules. **Propensity never establishes eligibility.**
- **Feature Store & Propensity Models**: Predicts likelihood of uptake among strictly *eligible* customer cohorts.
- **Deterministic Carbon Engine**: Computes sustainability impact using documented DEFRA/UK Government 2026 conversion factors.
- **LLM Grounding Layer**: Explains structured outputs in plain English under strict zero-hallucination constraints (via `grounding.py`).

```
                    ┌──────────────────────────────────────────────┐
                    │               Customer 360                   │
                    │   (Transactions, Demographics, Products)     │
                    └──────────────────────┬───────────────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        ▼                                     ▼
     ┌─────────────────────────────────────┐  ┌─────────────────────────────────┐
     │   Exclusion & Eligibility Engine    │  │    Customer Feature Store       │
     │     (Deterministic Rule Checks)     │  │  (6-Mo Window Aggregations)     │
     └──────────────────┬──────────────────┘  └───────────────┬─────────────────┘
                        │                                     │
           [Is Eligible == False]                             │
           ┌────────────┴────────────┐                        │
           ▼                         ▼                        ▼
     ┌───────────┐             ┌───────────┐      ┌─────────────────────────┐
     │  EXCLUDED │             │ QUALIFIED │─────►│   Propensity Models     │
     │ Reason    │             └───────────┘      │   (XGBoost / LightGBM)  │
     │ Codes     │                                └───────────┬─────────────┘
     └───────────┘                                            │
                                                              ▼
                                                  ┌─────────────────────────┐
                                                  │  Deterministic Carbon   │
                                                  │         Engine          │
                                                  └───────────┬─────────────┘
                                                              │
                                                              ▼
                                                  ┌─────────────────────────┐
                                                  │   Frozen JSON Payload   │
                                                  │       Contract          │
                                                  └───────────┬─────────────┘
                                                              │
                                                              ▼
                                                  ┌─────────────────────────┐
                                                  │ Grounded LLM Explainer  │
                                                  │   & Regex Validator     │
                                                  └─────────────────────────┘
```

---

## 2. Cutoff Date & Outcome Window Architecture

To eliminate temporal data leakage and provide consistent evaluation benchmarks across model training, validation, and production scoring, the observation and evaluation windows are frozen as follows:

```
                  HISTORICAL OBSERVATION WINDOW           OUTCOME / EVALUATION WINDOW
                  (Feature Engineering & State)           (Campaign Take-Up & Ground Truth)
          ├─────────────────────────────────────────┼─────────────────────────────────────────┤
     2026-01-01                                2026-06-30                                2026-12-31
     00:00:00 UTC                              23:59:59 UTC                              23:59:59 UTC
                                                     ▲
                                                     │
                                            CUTOFF DATE (T₀)
                                         2026-06-30 23:59:59 UTC
```

### 2.1 Historical Feature Observation Window
- **Start Timestamp**: `2026-01-01T00:00:00Z`
- **End Timestamp**: `2026-06-30T23:59:59Z`
- **Window Length**: Exactly 6 calendar months (181 calendar days).
- **Scope & Aggregations**:
  - Customer 360 profile snapshots (demographics, property tenure, account tenure).
  - Transaction categorisation across the 8 mutually exclusive taxonomy categories: `Fuel`, `Electricity`, `Gas`, `Public Transport`, `Home Improvement`, `Automotive`, `Utilities`, `Other`.
  - Aggregated behavioral metrics: Total fuel spend (£), electricity spend (£/kWh), gas spend (£/kWh), paper statement counts, digital channel login frequency.
  - Ownership states at snapshot date: Vehicle ownership, EV flag, property ownership, solar installation flag.

### 2.2 Cutoff Freeze Timestamp ($T_0$)
- **Cutoff Date**: `2026-06-30`
- **Cutoff Timestamp**: `2026-06-30T23:59:59Z`
- **Role**: All eligibility gates, exclusion evaluations, and feature generation vectors evaluate the customer's state exactly at $T_0$.

### 2.3 Campaign / Take-Up Outcome Window
- **Start Timestamp**: `2026-07-01T00:00:00Z`
- **End Timestamp**: `2026-12-31T23:59:59Z`
- **Window Length**: Exactly 6 calendar months (184 calendar days).
- **Scope & Role**:
  - Ground truth label generation: Customer take-up / conversion for products `GP01`, `GP02`, `GP03`, `GP04`.
  - Conversion tracking and performance benchmarking (Precision, Recall, ROC-AUC).

### 2.4 Strict Leakage Prevention Guarantees
1. **Zero Disjoint Overlap**: $\text{Observation Window} \cap \text{Outcome Window} = \emptyset$.
2. **Temporal Integrity**: Transactions, credit inquiries, product applications, or status shifts occurring on or after `2026-07-01T00:00:00Z` are strictly excluded from feature creation and exclusion checks at $T_0$.
3. **Reproducibility**: Downstream backtesting and scenario reruns against any historical customer record will yield deterministic exclusion and feature outputs.

---

## 3. Product Catalogue Mapping (GP01 – GP04)

The platform supports four primary green financial products. Eligibility criteria, target personas, customer signals, and carbon levers are codified below:

| Product Code | Opportunity Key | Product Name | Target Customer Segment | Primary Signals | Disqualification Triggers |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **GP01** | `GREEN_HOME` | Green Home Retrofit Loan | Homeowners in inefficient homes (EPC D–G) | High gas spend, low EPC, homeownership | Non-owner, EPC A/B, distress |
| **GP02** | `SOLAR_FINANCE` | Solar PV & Battery Finance | Homeowners with high power bills & private roofs | High power spend, detached/semi-detached | Non-owner, existing solar, flats |
| **GP03** | `EV_FINANCE` | Clean Transport & EV Finance | ICE drivers with high fuel spend & mileage | Fuel spend >£120/mo, vehicle loan | Already EV owner, no vehicle |
| **GP04** | `PAPERLESS_BANKING` | Paperless & Digital Journey | Active digital app users receiving paper bills | Paper statements, frequent app logins | Already paperless, no digital app |

> [!NOTE]
> **Catalogue Alias Mapping**: In the preliminary hackathon slide deck (Slide 4), products were numbered as GP01 EV, GP02 Green Home, GP03 Solar, GP04 Paperless. The engine supports dual resolution: canonical mapping maps `GP01` to `GREEN_HOME` and `GP02` to `SOLAR_FINANCE`, while maintaining full backward-compatibility with deck aliases via normalized `opportunity` strings (`GREEN_HOME`, `SOLAR_FINANCE`, `EV_FINANCE`, `PAPERLESS_BANKING`).

### 3.1 GP01 — Green Home Retrofit Loan (`GREEN_HOME`)
- **Use Case**: Energy-efficiency retrofits (cavity/loft insulation, double/triple glazing, heat pump conversions, thermostatic radiator controls).
- **Target Persona**: Homeowners occupying dwellings with poor or mediocre Energy Performance Certificates (EPC ratings D, E, F, or G) experiencing elevated heating/gas bills.
- **Inclusion Signals**:
  - `homeowner_status == 'OWNER'`
  - `property_epc_rating in ['D', 'E', 'F', 'G']`
  - High winter heating spend (`gas_spend_6m > £600` or `utilities_spend_6m > £1,200`)
- **Carbon Accounting Lever**: Displaces natural gas combustion (DEFRA 2026 factor: `0.18231 kg CO2e/kWh gross CV`) via insulation efficiency (typically 15–35% reduction in heating demand) or heat pump coefficient of performance (COP 3.0+).

### 3.2 GP02 — Solar PV & Battery Storage Finance (`SOLAR_FINANCE`)
- **Use Case**: Rooftop solar photovoltaic array (typically 3.5 kWp to 5.0 kWp) and domestic battery energy storage installation.
- **Target Persona**: Owner-occupiers with independent roof ownership living in detached, semi-detached, or end-terrace homes with substantial baseline daytime electricity consumption.
- **Inclusion Signals**:
  - `homeowner_status == 'OWNER'`
  - `property_type in ['DETACHED', 'SEMI_DETACHED', 'TERRACED']`
  - `has_solar == False`
  - Baseline electricity usage `> 3,000 kWh/year` (or `electricity_spend_6m > £450`)
- **Carbon Accounting Lever**: Displaces UK grid electricity (DEFRA 2026 factor: `0.13096 kg CO2e/kWh` generation + `0.01299 kg CO2e/kWh` T&D losses = `0.14395 kg CO2e/kWh`).

### 3.3 GP03 — Clean Transport & EV Finance (`EV_FINANCE`)
- **Use Case**: Personal auto loans / leasing for new or approved pre-owned Battery Electric Vehicles (BEVs), replacing fossil-fuel internal combustion engine (ICE) vehicles.
- **Target Persona**: Active drivers with verified recurring spend on petrol or diesel, or active ICE vehicle loans, clocking moderate-to-high annual commuting mileage (>8,000 miles/yr).
- **Inclusion Signals**:
  - `has_vehicle == True`
  - `is_ev_owner == False`
  - Recurring fuel spend (`fuel_spend_6m > £720`, equivalent to >£120/mo)
- **Carbon Accounting Lever**: Avoided tailpipe & lifecycle fuel emissions: Petrol car (`0.17048 kg CO2e/km`) or Diesel car (`0.17265 kg CO2e/km`) displaced by BEV grid charging (`0.06012 kg CO2e/km`), delivering net avoided emissions of `~0.11036 kg CO2e/km`.

### 3.4 GP04 — Paperless Banking & Digital Journey (`PAPERLESS_BANKING`)
- **Use Case**: Transition customer accounts from physical mailings (paper statements, transaction advices) to authenticated digital channels (mobile app push notifications, e-statements).
- **Target Persona**: Active users of mobile/online banking who continue to receive printed paper statements by default.
- **Inclusion Signals**:
  - `is_paperless == False` (receives paper statements)
  - `digital_logins_90d >= 1` (verified digital literacy and channel adoption)
  - Active verified digital contact (email or registered mobile device)
- **Carbon Accounting Lever**: Material and logistics avoidance: DEFRA 2026 primary paper factor `1,198.24 kg CO2e/tonne` (equivalent to `~1.20 g CO2e/g paper`) + mail transit emissions saved per paperless conversion (~360 g to 750 g $\text{CO}_2\text{e}$/year per customer).

---

## 4. Exclusion Rules Engine Architecture

### 4.1 Governance & Principles
1. **Pre-Scoring Execution**: The Exclusion Engine executes *prior* to or *in parallel with* propensity calculation. If a customer is disqualified, they are marked `is_eligible = false`, and are blocked from recommendation delivery.
2. **Fail-Closed Default**: If a mandatory field required for eligibility validation is missing or unverifiable, the rule defaults to exclusion to safeguard regulatory compliance.
3. **Immutable Rule Logic**: Every exclusion rule is expressed as an explicit, side-effect-free pure function returning a boolean flag and its standardized reason code.
4. **Audit Trail**: Every exclusion decision produces a persistent timestamped evaluation record containing all violated rule codes.

### 4.2 Exclusion Execution Matrix

```
┌───────────────────────────────────┬────────┬────────┬────────┬────────┬──────────────────────────────┐
│ Rule Check Description            │  GP01  │  GP02  │  GP03  │  GP04  │ Primary Reason Code Trigger  │
├───────────────────────────────────┼────────┼────────┼────────┼────────┼──────────────────────────────┤
│ Non-homeowner / Tenant            │  APPLY │  APPLY │    -   │    -   │ EXC_NOT_HOMEOWNER            │
│ Already owns Battery EV           │    -   │    -   │  APPLY │    -   │ EXC_ALREADY_EV_OWNER         │
│ Already enrolled in paperless     │    -   │    -   │    -   │  APPLY │ EXC_ALREADY_PAPERLESS        │
│ Solar PV already installed        │    -   │  APPLY │    -   │    -   │ EXC_ALREADY_SOLAR_INSTALLED  │
│ Property EPC already Grade A or B │  APPLY │    -   │    -   │    -   │ EXC_PROPERTY_MAX_EFFICIENCY  │
│ Flat / Apartment / Shared roof    │    -   │  APPLY │    -   │    -   │ EXC_PROPERTY_TYPE_INELIGIBLE │
│ No vehicle ownership / fuel spend │    -   │    -   │  APPLY │    -   │ EXC_NO_VEHICLE_USAGE         │
│ No digital channel / App access   │    -   │    -   │    -   │  APPLY │ EXC_NO_DIGITAL_CHANNEL       │
│ Active arrears / credit distress  │  APPLY │  APPLY │  APPLY │    -   │ EXC_FINANCIAL_DISTRESS       │
│ Customer marketing opt-out        │  APPLY │  APPLY │  APPLY │  APPLY │ EXC_MARKETING_OPT_OUT        │
│ Recent credit decline (90-day)    │  APPLY │  APPLY │  APPLY │    -   │ EXC_RECENT_APPLICATION_DECLINE│
│ Underage (<18) or Non-UK resident │  APPLY │  APPLY │  APPLY │  APPLY │ EXC_AGE_OR_RESIDENCY_INELIGIBLE│
└───────────────────────────────────┴────────┴────────┴────────┴────────┴──────────────────────────────┘
```

---

## 5. Standardized Reason Code Master List

The following **12 standardized, immutable exclusion reason codes** are registered in the schema dictionary. Downstream components (APIs, logs, and audit stores) must strictly adhere to these strings.

### 1. `EXC_NOT_HOMEOWNER`
- **Applicable Products**: `GP01` (Green Home), `GP02` (Solar Finance)
- **Business Logic**: `customer.homeowner_status != 'OWNER'`
- **Rationale**: Solar panels and structural retrofits require legal title to modify the building fabric and roof structure. Tenants and lodgers cannot authorize permanent property alterations.

### 2. `EXC_ALREADY_EV_OWNER`
- **Applicable Products**: `GP03` (EV Finance)
- **Business Logic**: `customer.is_ev_owner == True`
- **Rationale**: Mandated by Problem Statement 1 FR7 ("*Never recommend products the customer's data rules out, e.g. EV finance for an EV owner with no replacement use case*"). Prevents mis-targeting existing clean technology adopters.

### 3. `EXC_ALREADY_PAPERLESS`
- **Applicable Products**: `GP04` (Paperless Banking)
- **Business Logic**: `customer.is_paperless == True`
- **Rationale**: Customer is already enrolled in 100% digital correspondence; marketing paperless conversion provides zero incremental environmental benefit.

### 4. `EXC_ALREADY_SOLAR_INSTALLED`
- **Applicable Products**: `GP02` (Solar Finance)
- **Business Logic**: `customer.has_solar == True`
- **Rationale**: Property already has an operational solar photovoltaic system; cannot target initial solar adoption finance.

### 5. `EXC_PROPERTY_MAX_EFFICIENCY`
- **Applicable Products**: `GP01` (Green Home)
- **Business Logic**: `customer.property_epc_rating in ['A', 'B']`
- **Rationale**: Homes with EPC Rating A or B already operate at top-tier UK energy standards; retrofit loans offer negligible marginal heat-loss reduction.

### 6. `EXC_PROPERTY_TYPE_INELIGIBLE`
- **Applicable Products**: `GP02` (Solar Finance)
- **Business Logic**: `customer.property_type in ['FLAT', 'APARTMENT', 'MAISONETTE_SHARED']`
- **Rationale**: Multi-occupancy flat blocks have shared roofs governed by communal freeholds/leaseholds, barring individual domestic solar PV installations.

### 7. `EXC_NO_VEHICLE_USAGE`
- **Applicable Products**: `GP03` (EV Finance)
- **Business Logic**: `customer.has_vehicle == False and customer.fuel_spend_6m == 0`
- **Rationale**: Customers without cars or automotive fuel spend have no personal transport emissions to abate via an EV loan.

### 8. `EXC_NO_DIGITAL_CHANNEL`
- **Applicable Products**: `GP04` (Paperless Banking)
- **Business Logic**: `customer.has_digital_banking == False or customer.digital_logins_90d == 0`
- **Rationale**: Safeguards vulnerable or digitally excluded customers who rely on physical statements for financial access.

### 9. `EXC_FINANCIAL_DISTRESS`
- **Applicable Products**: `GP01`, `GP02`, `GP03` (All Credit Facilities)
- **Business Logic**: `customer.is_in_arrears == True or customer.delinquency_status != 'CURRENT'`
- **Rationale**: Regulatory compliance with FCA Consumer Duty and Lending Standards. Customers in active debt distress must never be cross-sold new credit facilities.

### 10. `EXC_MARKETING_OPT_OUT`
- **Applicable Products**: `GP01`, `GP02`, `GP03`, `GP04` (All Marketing Campaigns)
- **Business Logic**: `customer.marketing_consent == False`
- **Rationale**: Legal compliance with UK GDPR Article 21 and Privacy and Electronic Communications Regulations (PECR).

### 11. `EXC_RECENT_APPLICATION_DECLINE`
- **Applicable Products**: `GP01`, `GP02`, `GP03` (Credit Facilities)
- **Business Logic**: `customer.days_since_last_credit_decline < 90`
- **Rationale**: Cooling-off safeguard to avoid successive credit score impairments following an adverse credit decision within the preceding quarter.

### 12. `EXC_AGE_OR_RESIDENCY_INELIGIBLE`
- **Applicable Products**: `GP01`, `GP02`, `GP03`, `GP04`
- **Business Logic**: `customer.age < 18 or customer.uk_resident == False`
- **Rationale**: Minimum legal borrowing age in the UK is 18; green financing products require permanent UK tax and territorial residency.

---

## 6. Frozen JSON Schema Contract Alignment

The targeting output directly matches and extends the platform's JSON schema contract, ensuring seamless downstream consumption by the Carbon Engine, the LLM Grounding layer (`grounding.py`), and the Streamlit UX.

### 6.1 Targeting Decision Schema (`TargetingDecision`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "TargetingDecision",
  "type": "object",
  "required": [
    "customer_id",
    "product_code",
    "opportunity",
    "cutoff_date",
    "is_eligible",
    "targeting_status",
    "exclusion_reason_codes",
    "propensity",
    "confidence",
    "reason_codes"
  ],
  "properties": {
    "customer_id": {
      "type": "string",
      "pattern": "^C[0-9]{5,}$",
      "description": "Unique anonymized customer identifier (e.g. C10001)"
    },
    "product_code": {
      "type": "string",
      "enum": ["GP01", "GP02", "GP03", "GP04"],
      "description": "Standard product catalogue identifier"
    },
    "opportunity": {
      "type": "string",
      "enum": ["GREEN_HOME", "SOLAR_FINANCE", "EV_FINANCE", "PAPERLESS_BANKING"],
      "description": "Targeting opportunity category key"
    },
    "cutoff_date": {
      "type": "string",
      "format": "date",
      "example": "2026-06-30",
      "description": "Snapshot cutoff date for feature observation"
    },
    "is_eligible": {
      "type": "boolean",
      "description": "True if customer passed all business exclusion rules"
    },
    "targeting_status": {
      "type": "string",
      "enum": ["QUALIFIED", "EXCLUDED"],
      "description": "High-level qualification status"
    },
    "exclusion_reason_codes": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": [
          "EXC_NOT_HOMEOWNER",
          "EXC_ALREADY_EV_OWNER",
          "EXC_ALREADY_PAPERLESS",
          "EXC_ALREADY_SOLAR_INSTALLED",
          "EXC_PROPERTY_MAX_EFFICIENCY",
          "EXC_PROPERTY_TYPE_INELIGIBLE",
          "EXC_NO_VEHICLE_USAGE",
          "EXC_NO_DIGITAL_CHANNEL",
          "EXC_FINANCIAL_DISTRESS",
          "EXC_MARKETING_OPT_OUT",
          "EXC_RECENT_APPLICATION_DECLINE",
          "EXC_AGE_OR_RESIDENCY_INELIGIBLE"
        ]
      },
      "description": "List of immutable exclusion reason codes triggered"
    },
    "propensity": {
      "type": ["number", "null"],
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "ML model predicted probability of uptake (null if excluded)"
    },
    "confidence": {
      "type": ["number", "null"],
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Reliability score of the estimate (null if excluded)"
    },
    "reason_codes": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Positive recommendation drivers (empty if excluded)"
    },
    "sustainability_impact": {
      "type": ["object", "null"],
      "properties": {
        "estimated_annual_reduction_kg": { "type": "number" },
        "unit": { "type": "string", "default": "kg CO2e" },
        "method": { "type": "string" }
      }
    }
  }
}
```

### 6.2 Sample Contract Payloads

#### Example A: Qualified Recommendation (EV Finance `GP03`)
```json
{
  "customer_id": "C10001",
  "product_code": "GP03",
  "opportunity": "EV_FINANCE",
  "cutoff_date": "2026-06-30",
  "is_eligible": true,
  "targeting_status": "QUALIFIED",
  "exclusion_reason_codes": [],
  "propensity": 0.84,
  "confidence": 0.87,
  "reason_codes": [
    "HIGH_FUEL_SPEND",
    "HIGH_ANNUAL_MILEAGE",
    "EXISTING_VEHICLE"
  ],
  "sustainability_impact": {
    "estimated_annual_reduction_kg": 1200.0,
    "unit": "kg CO2e",
    "method": "GHG Protocol project emissions accounting"
  }
}
```

#### Example B: Excluded Customer (Solar Finance `GP02` — Non-Homeowner)
```json
{
  "customer_id": "C10042",
  "product_code": "GP02",
  "opportunity": "SOLAR_FINANCE",
  "cutoff_date": "2026-06-30",
  "is_eligible": false,
  "targeting_status": "EXCLUDED",
  "exclusion_reason_codes": [
    "EXC_NOT_HOMEOWNER"
  ],
  "propensity": null,
  "confidence": null,
  "reason_codes": [],
  "sustainability_impact": null
}
```

#### Example C: Excluded Customer (EV Finance `GP03` — Existing EV Owner)
```json
{
  "customer_id": "C10088",
  "product_code": "GP03",
  "opportunity": "EV_FINANCE",
  "cutoff_date": "2026-06-30",
  "is_eligible": false,
  "targeting_status": "EXCLUDED",
  "exclusion_reason_codes": [
    "EXC_ALREADY_EV_OWNER"
  ],
  "propensity": null,
  "confidence": null,
  "reason_codes": [],
  "sustainability_impact": null
}
```

---

## 7. Implementation & Verification Checklist

| Requirement | Implementation Artifact | Status |
| :--- | :--- | :--- |
| **Observation & Outcome Windows** | Section 2: Disjoint `Jan–Jun 2026` vs `Jul–Dec 2026`, Cutoff `2026-06-30` | **FROZEN** |
| **Product Catalogue (GP01–GP04)** | Section 3: Target use cases, signals, carbon levers | **FROZEN** |
| **Hardcoded Exclusion Logic** | Section 4: Rules engine matrix, fail-closed policy | **FROZEN** |
| **12 Reason Codes Master List** | Section 5: Exact 12 standardized, immutable codes | **FROZEN** |
| **JSON Contract Alignment** | Section 6: Matches `grounding.py` and demo payload schema | **FROZEN** |

---
*Authorized for Megathon X Hackathon Implementation — Team Singularity*
