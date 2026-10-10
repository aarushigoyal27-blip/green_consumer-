# Merge notes

## Source → destination
| Uploaded | Went to | Note |
|---|---|---|
| `person_c_engines.zip` | base of repo: `src/`, `config/`, `scripts/`, `tests/`, `docs/carbon_methodology.md`, `exclusion_engine.py` | Newest carbon + recommend engines |
| `src.zip`, `tests.zip` | *(not copied as-is)* | Older snapshots of the carbon engine/tests (smaller; no `recommend/`, no MGD003). `test_grounding.py` and `test_exclusion_vocab.py` were unique and kept |
| `exclusion_engine.py`, `contract.json` | identical to the copies in `person_c_engines`; one copy each (`config/contract.json`) | |
| `grounding.py` | `grounding.py` | one fix, below |
| `process_csv.py` | `scripts/grounding_csv_demo.py` | now defaults to `config/raw/desnz_extract.csv` |
| `benchmark_llm.py` | `scripts/benchmark_llm.py` | `tests/test_llm.py` was an identical copy that calls a live API at import — dropped |
| `step6.py`, `step7.py` | `scripts/data/` | numbering fix + repo-relative paths |
| `csv_files.zip` | `data/*.csv`, `data/*.json` | take-up columns relabelled (below) |
| `emission.csv` | = `config/raw/desnz_extract.csv` (identical) | duplicate dropped |
| `green_products.csv` | `config/green_products.csv` | |
| `green_consumer-.zip` | `app/` (Streamlit), `docs/` (templates) | its copies of engine/grounding/contract were identical to the above |
| `PRODUCT_TARGETING_EXCLUSION_DESIGN.md` | `docs/` | superseded banner added |
| `README.md` | replaced by a new README | old one described GP01 = Green Home and 12 codes that no longer match the contract |
| `requirements-carbon.txt` | merged into `requirements.txt` | |

## Changes to your code/data
1. **`take_up_GP01/02/03` labels were mis-numbered** in `customer_360.csv` and `synthetic_customers.csv`
   (GP01 = green-home, GP02 = solar, GP03 = EV vs the contract's EV / green-home / solar). Columns renamed
   (data unchanged otherwise): positives GP01 271→497 (EV), GP02 148→271 (Green Home), GP03 497→148 (Solar).
   `step6` fixed so regeneration is correct.
2. **`grounding.UnsupportedNumber.__eq__`**: a flagged `£400k` now also equals `400000`
   (previously only `400`). Detection behaviour is unchanged.
3. **`tests/acceptance`: vulnerable-customer test rewritten** — it passed `delinquency_status="VULNERABLE"`,
   which contract v2.1.0 rejects; vulnerability is read only from `vulnerability_flag`
   (→ `requires_human_review`). Added a test that the unknown value is rejected.
4. Contract tests now look in `config/contract.json`, so 3 + 8 previously-skipped tests run.
5. New `tests/integration/test_customer360_end_to_end.py` (data → exclusion → recommend → carbon).

## Results
- 178 tests passed (was: 1 failing + 11 skipped in `person_c_engines`; 1 failing + 1 import error in `green_consumer-`).
- All 5,000 `customer_360` rows pass the exclusion engine's vocabulary check.
- Fixed `step6` regenerates correctly-labelled data (verified); the guard test fails if the old numbering returns.
