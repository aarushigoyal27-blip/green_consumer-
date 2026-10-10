# Green Customer Insights Platform — Megathon X (PS1 · Lloyds)

Turns customer behaviour into green financial opportunities (EV Finance, Green Home, Solar,
Paperless) with estimated impact and plain-language explanations.

**Core rule:** ML models *predict* · the carbon engine *computes* impact · the LLM only *explains*
structured outputs · a propensity never establishes eligibility.

```
customer_360.csv ─► exclusion_engine ─► recommend engine ◄─ ML propensities (person B)
                    (who may be         │   ▲
                     targeted)          │   └─ carbon engine (kg CO2e / kWh / kg paper)
                                        ▼
                              structured record ─► grounding.explain() ─► grounding.validate()
                                                    (LLM text)           (blocks invented numbers)
```

## Product numbering (frozen — `config/contract.json` v2.1.0)

| Code | Opportunity key | Product |
|------|-----------------|---------|
| GP01 | `EV_FINANCE` | EV Finance |
| GP02 | `GREEN_HOME` | Green Home Loan |
| GP03 | `SOLAR_FINANCE` | Solar Finance |
| GP04 | `PAPERLESS_BANKING` | Paperless Banking |

Inside the recommend engine everything is keyed by **opportunity name**; GP codes only appear in
output records. Data label columns are `take_up_GP01 … take_up_GP04` using the numbering above.

Windows: cutoff `2026-06-30` · features `2026-01-01 → 2026-06-30` · outcomes `2026-07-01 → 2026-12-31`.

## Repository layout

```
exclusion_engine.py      Deterministic targeting/exclusion rules (contract v2.1.0)
grounding.py             explain() + validate(): LLM text with a number-level hallucination check
src/engine/carbon/       Carbon engine (DESNZ 2026 factors, MCS MGD003 solar table, YAML assumptions)
src/engine/recommend/    Recommendation engine: exclusion adapter, propensity I/O, thresholds, ranking
config/                  contract.json (single copy), emission_factors.csv, carbon_assumptions.yaml,
                         mcs_mgd003_pv_only.csv, green_products.csv, raw/ (source DESNZ/MCS/NEED files)
data/                    customer_360.csv, synthetic_customers.csv, synthetic_transactions.csv,
                         training_data.json, stress_test_data.json   (all synthetic)
scripts/                 demo_recommend.py, check_submission_ready.py, build_* (factor tables),
                         grounding_csv_demo.py, benchmark_llm.py
scripts/data/            step6 (synthetic customers + transactions) → step7 (customer_360)
app/                     Streamlit app (run from here)
docs/                    Methodology, design docs, data card, eval report, responsible-AI note
tests/                   carbon/, recommend/, acceptance/, integration/, grounding, vocabulary guard
archive/                 Superseded files kept for reference (see archive/README.md)
```

## Quickstart

```bash
pip install -r requirements.txt
python -m pytest -q                          # 178 tests
python scripts/demo_recommend.py --engine    # end-to-end demo with the real exclusion engine
python scripts/check_submission_ready.py     # checks factor tables match their raw sources
cd app && streamlit run app.py               # UI (pages are still placeholders — see below)
```

### Exclusion check

```python
import json
from exclusion_engine import evaluate_customer_targeting

base = json.load(open("config/contract.json"))["sample_payloads"]["sample_input_qualified_customer"]
tenant = {**base, "customer_id": "C10042", "homeowner_status": "TENANT"}

evaluate_customer_targeting(tenant, "GP02")["exclusion_reason_codes"]   # ['EXC_NOT_HOMEOWNER']
evaluate_customer_targeting(tenant, "GP01")["targeting_status"]         # 'QUALIFIED'
```

Three outcomes: `QUALIFIED`, `EXCLUDED`, `INSUFFICIENT_DATA` (missing data is never treated as a
negative fact). Unknown categorical values raise `UnknownVocabularyError` — call
`validate_records()` when loading data.

### Grounded explanation

```python
from grounding import explain, validate

payload = {"customer_id": "C10001", "opportunity": "EV_FINANCE", "propensity": 0.84,
           "confidence": 0.87, "annual_fuel_spend": 2400,
           "estimated_annual_reduction_kg": 1200, "unit": "kg CO2e", "special_grant": None}
text = explain(payload)
validate(text, payload)                        # []  -> every number is traceable to the payload
validate(text + " Save 5000 kg.", payload)     # [UnsupportedNumber('5000', ...)]
```

`validate` matches equivalent units (`1.2 t` ↔ `1200 kg`, `£350k` ↔ `350000`, `84%` ↔ `0.84`) and
ignores `CO2`/`CO2e` subscripts. `explain` supports Gemini, OpenAI-compatible endpoints, a custom
`llm_fn`, or a deterministic built-in generator. Copy `.env.example` → `.env` for the LLM benchmark.

### Regenerating the synthetic data

```bash
python scripts/data/step6_generate_synthetic.py && python scripts/data/step7_build_customer360.py
# GCI_DATA_DIR=/some/dir to write elsewhere. See Known issues #2 before overwriting data/customer_360.csv.
```

## Known issues / open decisions

1. **Labels include customers the rules would exclude.** 16–41% of positive `take_up_*` rows
   (EV 29%, Green Home 34%, Solar 41%, Paperless 16%) belong to customers the exclusion engine marks
   `EXCLUDED` — opted out, inactive account, in arrears, flat or existing solar. The label generator
   ignores those rules. **Train and evaluate only on `QUALIFIED` customer×product rows**, or regenerate
   labels with eligibility applied.
2. **`step6`/`step7` are behind `data/customer_360.csv`.** The shipped file has 7 columns the scripts do
   not produce (`account_status`, `annual_mileage_km`, `has_ice_vehicle`, `has_solar`,
   `paper_statements_per_year`, `property_type`, `vehicle_fuel_type`) and different baseline energy
   distributions, so the revision that generated it is missing from this repo. Regenerating gives
   correctly-labelled data but *without* those columns, and the exclusion/carbon engines need them.
3. **Feature window.** Contract and `step6` use a 6-month window (Jan–Jun, ×2 to annualise, no seasonal
   factor). `docs/design_decisions.md` §1 recommends a 12-month lookback and `archive/generate_data_12m_alt.py`
   implements it. Unresolved — pick one before final evaluation.
4. **App pages are still placeholders** (mock numbers, banners say so). The engines they should call
   are ready; wiring is the next step. `models/` and `predictions/` (checklist items C and I) do not exist yet.
5. **Propensities are stubs.** `write_stub_propensities` produces random numbers for plumbing only —
   never report metrics on them.

## What changed when these files were merged

See `MERGE_NOTES.md`.
