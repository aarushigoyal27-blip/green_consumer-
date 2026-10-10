# Evaluation Report – PS1

All metrics are on the **validation split** (customer-level, 300 customers), next to a simple baseline. Test-split scores are produced once by `train.py` and written to `predictions/test_predictions.csv`. Numbers come from different datasets and are not comparable with other teams' results. Regenerate every number with `python evaluate.py` (writes `results/eval.json`).

| Field | Value |
|---|---|
| Version | Repository state at submission |
| Date · author | 2026-10-11 · PS1 team |
| Seed(s) | 42 (data generation, split, models) |
| Reproduce with | `python generate_data.py --n 2000 --out data && python train.py && python evaluate.py` |

## 1. Data and splits
- Customer-level split 70 / 15 / 15: **1,400 train / 300 validation / 300 test** customers (see [data_card.md](data_card.md)). The split is made before any feature is built.
- Leakage checks: features use only data on or before the cutoff 2026-06-30 (enforced in `customer360.py`); take-up labels come only from 2026-07-01 to 2026-12-31; the hidden ground-truth traits in `data/_hidden/` are never read by the models; no customer appears in more than one split.

## 2. Results by component
| Component | Metric | Simple baseline | Our model | Notes |
|---|---|---|---|---|
| Transaction categoriser | Macro-F1 / accuracy | keyword rules: 0.878 / 0.889 | 0.999 / 1.000 | TF-IDF character n-grams + logistic regression, n=20,000 validation transactions. Near-perfect because merchant names come from a fixed set of templates; expect lower on real data. |
| EV propensity | PR-AUC / ROC-AUC / Brier | 0.299 / 0.750 / 0.057 | 0.285 / 0.777 / 0.058 | base rate 6.8%, n=205; Brier of always predicting the base rate 0.064 |
| Green Home propensity | PR-AUC / ROC-AUC / Brier | 0.451 / 0.776 / 0.090 | 0.372 / 0.775 / 0.094 | base rate 12.0%, n=158; Brier of always predicting the base rate 0.106 |
| Solar propensity | PR-AUC / ROC-AUC / Brier | 0.573 / 0.871 / 0.056 | 0.597 / 0.846 / 0.055 | base rate 8.5%, n=164; Brier of always predicting the base rate 0.078 |
| Paperless propensity | PR-AUC / ROC-AUC / Brier | 0.680 / 0.847 / 0.135 | 0.645 / 0.828 / 0.138 | base rate 26.5%, n=185; Brier of always predicting the base rate 0.195 |
| Confidence | – | – | not calibrated | Confidence is the share of a model's inputs that are present. It is **not** a calibrated probability and is not evaluated against error. |
| Carbon engine | hand-checked cases pass | n/a | 6 of 6 | deterministic |

**Reading the propensity results.** With 700–900 training rows per product, a gradient-boosted model is not clearly better than a logistic regression. The logistic model is ahead on PR-AUC for EV, Green Home and Paperless; the boosted model is ahead only for Solar. Both beat the base rate on every product. Predicted probabilities have a lower Brier score than always predicting the base rate, so they are informative, but they are weak for EV (PR-AUC 0.285 against a base rate of 6.8%).

## 3. LLM evaluation
| Metric | Result | Eval set size |
|---|---|---|
| Numeric faithfulness (every figure in the text is in the structured payload) | 200 of 200 | 200 explanations |
| Fabricated figure detected by the checker | 200 of 200 | 200 injected false claims |
| Forbidden claims (eligibility, guarantees) | payload always carries `eligibility: NOT_ASSESSED`; the prompt forbids guarantees | rule check |
- Method: rule check. `grounding.validate()` extracts every number from the text and checks it against the payload, including unit conversions. False claims are injected with `simulate_hallucination()`.
- Scope: these results use the built-in reference explainer. They show the checker works; they do not measure any particular external LLM. When Gemini or OpenAI is configured, the same check runs on its output and the page flags unsupported numbers.

## 4. Scenario tests
| Scenario | Expected | Observed | Pass |
|---|---|---|---|
| Missing vehicle data | INSUFFICIENT_DATA | INSUFFICIENT_DATA | ✔ |
| EV owner with no petrol/diesel car, EV Finance | EXCLUDED | EXCLUDED | ✔ |
| Tenant, Solar Finance | EXCLUDED | EXCLUDED | ✔ |
| Marketing opt-out | EXCLUDED | EXCLUDED | ✔ |
| Unknown consent (null) | INSUFFICIENT_DATA | INSUFFICIENT_DATA | ✔ |
| Insufficient impact data (no electricity) | None | None | ✔ |
| Customer goes paperless: output updates | QUALIFIED -> EXCLUDED | QUALIFIED -> EXCLUDED | ✔ |

## 5. Error analysis and limitations
- Training data is small (700–900 labelled rows per product) and synthetic; the labels are generated from a known formula, so results show the pipeline works, not how it would perform on real customers.
- EV take-up is the weakest model: the generator makes it depend partly on the hidden eco-mindedness trait, which the models cannot see.
- Two segments are recommended much less often than others; see the fairness section of [responsible_ai_note.md](responsible_ai_note.md).
- Not claimed: eligibility, guaranteed impact, calibrated confidence.

## 6. System performance
| Measure | Value |
|---|---|
| Decision latency, rules + model + carbon engine (no LLM) | about 6.1 ms per customer × product |
| Batch scoring | 2,000 customers × 4 products scored on dashboard load (one cached run) |
