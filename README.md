# PS1 · Green Customer Insights Platform (Megathon X)

Finds customers who may want a green financial product (EV Finance, Green Home, Solar, Paperless), estimates the carbon impact, and explains each result in plain language.

**Core rule:** ML models predict · rules decide who may be offered a product · the carbon engine computes impact · the LLM only explains structured outputs.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
On first start the app generates the synthetic data (`data/`) and trains the models; this takes about a minute. To do these steps yourself and save the outputs:
```bash
python generate_data.py --n 2000 --out data   # synthetic data, seed 42
python train.py                               # models/, predictions/test_predictions.csv
python evaluate.py                            # results/eval.json used by the Evaluation page
```
Optional: set `GEMINI_API_KEY` or `OPENAI_API_KEY` to have a real LLM write the explanations (every figure in its text is checked against the data). Without a key a built-in grounded template is used.

## How it fits together
`customer360.py` (one table per customer) → `exclusion_engine.py` (who may be offered what) → `pipeline.py` (propensity, reason codes) → `carbon_engine.py` (impact from `emission.csv`) → `grounding.py` (explanation + number check) → Streamlit pages.

## Files
- Pages: `app.py`, `home.py`, `ps1_customer.py`, `ps1_business.py`, `data_labels.py`, `evaluation.py`, `explainability.py`, `architecture.py`, `docs_viewer.py`, `ui.py`
- Documents: `data_card.md`, `label_rules.md`, `eval_report.md`, `responsible_ai_note.md`, `design_decisions.md`, `PRODUCT_TARGETING_EXCLUSION_DESIGN.md`, `architecture.mmd`, `contract.json`
- Tests: `test_exclusion_engine.py`, `test_grounding.py`
