# Label Rules – PS1

Labels are plausible functions of input features plus documented noise, never arbitrary. Every rule below is implemented in `generate_data.py` and reproducible from seed 42.

## 1. Transaction category (FR2)
Exactly one category per transaction, mutually exclusive:
`Fuel · Electricity · Gas · Public Transport · Home Improvement · Automotive · Utilities · Other`

| Category | Merchant / keyword rule | Priority |
|---|---|---|
| Fuel | pump fuel: forecourt brands (Shell, BP, Esso, Texaco, Gulf, Jet, Murco, Applegreen) and supermarket petrol (Tesco PFS, Asda Petrol, Morrisons Petrol, Sainsbury's Fuel) | 1 |
| Electricity | an energy account that names electricity only (e.g. "OVO ENERGY ELEC DD") | 2 |
| Gas | an energy account that names gas only (e.g. "EDF ENERGY GAS DD") | 2 |
| Public Transport | train, bus, tram and metro operators, TfL, Oyster, Trainline | 3 |
| Home Improvement | builders' merchants and DIY (B&Q, Wickes, Screwfix, Travis Perkins), insulation, glazing and joinery suppliers | 4 |
| Automotive | tyres, servicing, MOT, car wash, car parts, vehicle tax, breakdown cover | 5 |
| Utilities | dual-fuel supplier bills, water, broadband | 6 |
| Other | fallback for everything else | last |

**Boundary decisions** (applied consistently in the generator)
| Case | Decision | Rationale |
|---|---|---|
| Fuel vs Automotive (forecourt shop, car wash) | Pump fuel is Fuel. Car wash, servicing, MOT and tyres are Automotive, even at a forecourt brand ("SHELL CAR WASH" is Automotive) | Only fuel spend should drive EV signals |
| Electricity / Gas vs Utilities (dual-fuel or water bill) | A bill naming only one fuel is Electricity or Gas. A supplier billing both fuels, water and broadband is Utilities | Single-fuel spend can be linked to a product; dual-fuel cannot be split |
| Unknown merchant | Other | no guess |

**Method:** ☑ Rules (ground truth from the merchant template) ☑ ML (a TF-IDF + logistic regression categoriser is trained on the raw merchant text and evaluated in [eval_report.md](eval_report.md)) · **Tie-break order:** the priority column above.

## 2. Customer–product take-up (FR3)
Each eligible customer × product pair gets `p = sigmoid(intercept + weighted features + Normal(0, 0.9) noise)`. Features are standardised (z-scores). The intercept is solved so average take-up hits the target prevalence.

| Product | Take-up probability (inputs and weights) | Hard exclusions (never recommend) |
|---|---|---|
| GP01 EV Finance | 1.0·fuel spend + 0.9·eco-mindedness + 0.5·income + 0.4·vehicle age + 0.3·vehicle loan | no vehicle; EV owner with no replacement use (EV under 8 years old) |
| GP02 Green Home Loan | 0.9·energy use + 1.0·eco-mindedness + 0.4·income + 0.5·home-improvement spend + 0.3·mortgage | not a home owner |
| GP03 Solar Finance | 1.0·eco-mindedness + 1.1·electricity use + 0.5·income + 0.4·owns outright | not a home owner |
| GP04 Paperless Banking | 1.6·digital comfort + 0.5·eco-mindedness + 0.4·app logins | already on digital statements |

- All products also exclude a customer who already holds that product.
- Label draw: `y ~ Bernoulli(p)` · seed 42 · target prevalence among eligible customers: GP01 8%, GP02 10%, GP03 7%, GP04 25% (achieved 7.7%, 12.0%, 8.2%, 24.2%).
- Intended use split: Green Home finances cutting energy **demand** (insulation, glazing, heat pump, controls); Solar finances energy **generation** (panels, optionally with a battery). Reduces demand → Green Home; generates energy → Solar.
- **Eligibility is not a label.** It comes from product rules (`exclusion_engine.py`); a propensity never establishes it. Ineligible pairs get no label.

## 3. Reason codes (FR7)
| Code | Fires when | Products |
|---|---|---|
| `HIGH_FUEL_SPEND` | monthly fuel spend ≥ £150 | EV |
| `HIGH_ANNUAL_MILEAGE` | annual mileage ≥ 10,000 km | EV |
| `EXISTING_VEHICLE` | owns a petrol, diesel or hybrid vehicle | EV |
| `OLDER_VEHICLE` | vehicle age ≥ 8 years | EV |
| `EXISTING_VEHICLE_LOAN` | has an active vehicle loan | EV |
| `HIGH_ELECTRICITY_SPEND` | monthly electricity spend in the top quartile | Green Home, Solar |
| `HIGH_GAS_SPEND` | monthly gas spend in the top quartile | Green Home |
| `HOME_OWNER` | owns the home (mortgage or outright) | Green Home, Solar |
| `HOME_IMPROVEMENT_SPEND` | any home-improvement spend in the last 12 months | Green Home |
| `PAPER_STATEMENTS` | half or more statements on paper | Paperless |
| `HIGH_DIGITAL_ACTIVITY` | app and web logins in the last 3 months at or above the median | Paperless |

Up to three codes are shown per result, in the order above.

## 4. Noise, edge cases, scenario seeds
| Scenario | How injected | Expected behaviour |
|---|---|---|
| Missing / conflicting data | about 3% of vehicle owners lose mileage, about 2% lose vehicle age, about 4% of energy months are dropped | degrade gracefully; the engine flags missing fields (`INSUFFICIENT_DATA`) |
| Product that should not be recommended | EV owners, renters, customers already paperless or already holding the product | excluded with a reason code, not recommended |
| Insufficient impact data | no usable mileage, fuel spend, electricity or statement history | impact value is empty and shown as "not available" |
| Changed customer circumstances | change a field (e.g. paperless) and rerun | decision updates (tested in [eval_report.md](eval_report.md)) |

## 5. Validating the labels
- Sanity checks run by `generate_data.py` on every build: customer split about 70/15/15; no data after the cutoff; take-up dates inside Jul–Dec 2026; ineligible pairs unlabelled; prevalence per product; fuel spend relates to EV take-up but not perfectly (AUC 0.649, correlation 0.176, required to stay between 0.55 and 0.90).
- Known weaknesses: labels depend on hidden traits that the models cannot see, so achievable accuracy is limited by design; the formula is simple and linear; a larger dataset (`--n 20000`) gives more stable metrics.
