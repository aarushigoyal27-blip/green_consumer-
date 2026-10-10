# Carbon engine methodology (PS1)

## Framework
GHG Protocol project / avoided-emissions approach. For each product the engine compares a
**baseline scenario** (current behaviour) with a **project scenario** (after adopting the product)
over a **one-year horizon**: `avoided = baseline − project`.

Excluded: rebound effects, embodied (manufacturing) emissions, well-to-tank emissions.
**PCAF is not used**: it covers financed-emissions accounting of a lender's portfolio, which is
not what is estimated here.

The engine is deterministic: no ML, no eligibility decisions, no LLM. All factors come from
`config/emission_factors.csv` (UK DESNZ GHG conversion factors, sheet + row label recorded); all
other parameters from `config/carbon_assumptions.yaml`, each with a source.

## Formulas
| Product | Primary method | Fallback / edge cases |
|---|---|---|
| GP01 EV Finance | annual km × (petrol/diesel car per-km − BEV per-km) | No mileage: litres = fuel spend ÷ pump price; baseline = litres × per-litre factor; km = litres × (per-litre ÷ per-km factor); quality *low*. Neither → `insufficient_data`. Already EV → `not_applicable`. Unknown/hybrid fuel → petrol default, quality *medium* |
| GP03 Solar Finance | min(kWp × yield × self-consumption share, annual electricity use) × grid factor. Share from the MCS MGD 003 look-up (PV only), by occupancy archetype (default “In half the day”), annual-use band and generation band | No electricity data → `insufficient_data`. Use outside 1,500–5,999 kWh or generation ≥ 6,000 kWh → nearest band, quality *low*. Exported generation not credited |
| GP02 Green Home | Σ fuels: annual kWh × package reduction share × fuel factor | One fuel missing → `partial`, computed for the available fuel and stated. Both missing → `insufficient_data` |
| GP04 Paperless | statements/yr × pages × g/page → **kg paper** (headline) | Paper-production carbon on a separate labelled `supplementary` line. Digital adoption never counted as carbon. 0 statements → `not_applicable` |

Grid electricity factor = generation + T&D losses (consumer-side view), switchable via
`electricity_include_td`. Gas uses gross-CV kWh, matching UK bills.
BEV per-km factors are **derived**, because the DESNZ 2026 BEV rows could not be downloaded and
the one BEV value in our extract implied an implausible 0.42 kWh/km. Following the DESNZ method
(methodology report 2026: real-world Wh/km × UK electricity generation and T&D factors), we use
0.2171 kWh/km for an average electric car (Energy Saving Trust Fleet Decarbonisation Toolkit,
based on DESNZ 2025 factors) × the 2026 generation and T&D factors. The 2026 major-changes report
says new EVs became more efficient, so this slightly overstates EV emissions and understates GP01
savings (conservative). The BEV T&D component follows `electricity_include_td`, like household
electricity. Consistency check: BEV per-km ÷ grid per-kWh must imply
0.15–0.30 kWh/km (`test_real_bev_factor_consistent_with_grid_factor`).

## Missing data
`None` = missing, `0` = observed zero. Missing inputs are listed in `missing_fields`; never
silently treated as zero. Annualisation of monthly data happens upstream in features.

## Output contract
Every result carries `status`, `method`, `assumptions[]`, `factor_refs[]` (activity, value,
unit, year, DESNZ sheet, row label), `missing_fields[]`, `estimate_quality`, `is_estimate: true`.

## Factor provenance
`config/raw/desnz_extract.csv` is the DESNZ 2026 extract. `scripts/build_emission_factors.py`
selects one row per engine key by (activity, unit, row label) and writes
`config/emission_factors.csv`; `--check` fails if the two drift apart.

`config/mcs_mgd003_pv_only.csv` is extracted from `config/raw/MGD003-LookupTables-FINAL.xlsx`
by `scripts/build_mgd003_table.py` (`--check` detects drift).

## Pre-submission gate
`python scripts/check_submission_ready.py` exits non-zero while any assumption source still says
VERIFY or the factor CSV contains FILL.

## Verification
`pytest tests/carbon` — hand-calculated cases per product using synthetic round-number factors
(`tests/fixtures`), config-validation tests (missing activity, per-mile unit, duplicates), and a
plausibility check on the real DESNZ CSV.
