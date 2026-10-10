# Evaluation Report – PS1

> Report metrics on the **validation set**, next to a simple baseline. Metrics from different datasets are not comparable; say so. Regenerate all numbers with `TODO scripts/evaluate.py`.

| Field | Value |
|---|---|
| Version / git commit | `TODO` |
| Date · author | `TODO` |
| Seed(s) | `TODO` |
| Reproduce with | `TODO command` |

## 1. Data and splits
- Customer-level train / val / test sizes: `TODO` (see [data_card.md](data_card.md))
- Leakage checks: `TODO`

## 2. Results by component
| Component | Metric | Simple baseline | Our model | Notes |
|---|---|---|---|---|
| Transaction categoriser | Macro-F1, accuracy | keyword rules | | |
| EV propensity | PR-AUC, ROC-AUC, Brier | popularity / logistic reg. | | |
| Green Home propensity | same | | | |
| Solar propensity | same | | | |
| Paperless propensity | same | | | |
| Confidence | reliability vs actual error | | | |
| Carbon engine | hand-checked cases pass | n/a | | deterministic |

## 3. LLM evaluation
| Metric | Result | Eval set size |
|---|---|---|
| Groundedness (claims supported by structured input) | | |
| Numeric faithfulness (figures match engine output) | | |
| Forbidden claims (eligibility, guarantees) | | |
- Method (human / LLM-judge / rule check), prompt + model versions, failure examples: `TODO`

## 4. Scenario tests
| Scenario | Expected | Observed | Pass |
|---|---|---|---|
| Missing or conflicting data | Flagged, graceful | | ☐ |
| Product that should NOT be recommended (e.g. EV owner) | Not recommended | | ☐ |
| Insufficient impact data | "Insufficient data" | | ☐ |
| Changed customer circumstances | Output updates | | ☐ |

## 5. Error analysis and limitations
`TODO` · Not claimed: eligibility, guaranteed impact.

## 6. System performance
| Measure | Value |
|---|---|
| Inference latency (p50 / p95) | |
| Batch scoring throughput | |
