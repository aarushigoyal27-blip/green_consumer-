# Label Rules – PS1

> Labels must be **plausible functions of input features plus documented noise**, never arbitrary. Every rule must be implemented in code and reproducible from a seed.

## 1. Transaction category (FR2)
Exactly one category per transaction, mutually exclusive:
`Fuel · Electricity · Gas · Public Transport · Home Improvement · Automotive · Utilities · Other`

| Category | Merchant / MCC / keyword rule | Priority |
|---|---|---|
| Fuel | `TODO` | |
| Electricity | `TODO` | |
| Gas | `TODO` | |
| Public Transport | `TODO` | |
| Home Improvement | `TODO` | |
| Automotive | `TODO` | |
| Utilities | `TODO` | |
| Other | fallback | last |

**Boundary decisions** *(document and apply consistently)*
| Case | Decision | Rationale |
|---|---|---|
| Fuel vs Automotive (forecourt shop, car wash) | `TODO` | |
| Electricity / Gas vs Utilities (dual-fuel or water bill) | `TODO` | |
| Unknown merchant | `Other` | |

**Method:** ☐ Rules ☐ ML ☐ Embeddings · **Tie-break order:** `TODO`

## 2. Customer–product take-up (FR3)
| Product | Take-up probability (inputs, weights, noise) | Hard exclusions (never recommend) |
|---|---|---|
| GP01 EV Finance | `p = σ(β₀ + β₁·fuel_spend + β₂·mileage + …) + noise` | EV already owned, no replacement use case |
| GP02 Green Home Loan | `TODO` (mortgage / ownership, utility spend) | `TODO` |
| GP03 Solar Finance | `TODO` (ownership, electricity spend) | `TODO` |
| GP04 Paperless Banking | `TODO` (paper statements, digital activity) | Already paperless |

- Label draw: `y ~ Bernoulli(p)` · seed `TODO` · target prevalence `TODO %`
- Document the intended use-case split between Green Home and Solar so mapping is consistent.
- **Eligibility is not a label.** It comes from product rules; a propensity never establishes it.

## 3. Reason codes (FR7)
| Code | Fires when | Products |
|---|---|---|
| `HIGH_FUEL_SPEND` | `TODO` | EV |
| `HIGH_ANNUAL_MILEAGE` | `TODO` | EV |
| `EXISTING_VEHICLE` | `TODO` | EV |

## 4. Noise, edge cases, scenario seeds
| Scenario | How injected | Expected behaviour |
|---|---|---|
| Missing / conflicting data | `TODO` | Degrade gracefully, flag |
| Product that should not be recommended | `TODO` | Not recommended |
| Insufficient impact data | `TODO` | "Insufficient data" |
| Changed customer circumstances | `TODO` | Output updates |

## 5. Validating the labels
- Sanity checks (monotonic relationships, prevalence, feature correlation): `TODO`
- Known weaknesses: `TODO`
