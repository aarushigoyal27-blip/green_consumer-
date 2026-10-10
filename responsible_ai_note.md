# Responsible AI Note – PS1

> Required sections: privacy, bias, explainability, hallucination, human oversight, data limitations. Replace each `TODO` with specifics of *this* system.

## 1. Purpose and scope
What the system does, who uses it (customers, relationship teams), and what it must not be used for. `TODO`

## 2. Division of responsibility
| Component | Does | Must not |
|---|---|---|
| ML models | Predict propensity / scores | Decide eligibility |
| Carbon engine & calculators | Compute impact from documented formulas and factors | Be overridden by the LLM |
| LLM | Explain structured outputs; answer what-ifs *after* a rerun | Predict, calculate, invent figures, decide eligibility |
| Eligibility rules | Set by product rules and authorised processes | — |

## 3. Privacy
- Data used: synthetic / public only; no real personal or confidential banking data. `TODO confirm`
- What is sent to external LLM APIs (should be structured, minimised, non-identifying): `TODO`
- Logging and retention: `TODO`

## 4. Bias and fairness
- Features that may proxy protected traits (postcode, age, income, property type): `TODO`
- Checks run (take-up and recommendation rates by segment): `TODO`
- Risk of excluding renters / low-income / older housing stock from green offers: `TODO`
- Mitigations: `TODO`

## 5. Explainability
- Each recommendation shows: evidence, confidence, reason codes, data timestamp. ✔/☐
- Reason-code dictionary: `TODO`
- Customer-facing impact is labelled **estimate**, method noted; property value shown as a **range**.

## 6. Hallucination and misuse controls
| Risk | Control | Evidence |
|---|---|---|
| LLM invents numbers | Prompt receives structured JSON only; numeric-claim checker | `TODO` |
| LLM implies eligibility / guarantees | Prompt rules + output filter | |
| What-if without recompute | Orchestration forces rerun | |
| Prompt injection via free text | `TODO` | |

## 7. Human oversight
- Who reviews recommendations before outreach: `TODO`
- Override / appeal route; customer can ignore or decline: `TODO`
- Monitoring and drift review cadence: `TODO`

## 8. Data limitations and known risks
- Synthetic-data realism limits, label noise, emissions-factor vintage, valuation not causal. `TODO`

## 9. Sign-off
| Role | Name | Date |
|---|---|---|
| Author | | |
| Reviewer | | |
