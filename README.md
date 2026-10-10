# PS1 · Green Customer Insights Platform (Megathon X)

Streamlit shell with placeholder pages and documentation templates.

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Layout
Flat: all `.py` pages, `ui.py`, and the `.md`/`.mmd` docs sit next to `app.py`. Main file: `app.py`.

## Wiring real work in
1. Replace mock values in the page `.py` files with calls into your own modules.
2. Remove a page's placeholder banner (`header(..., todo=...)`) once it shows real output.
3. Fill `docs/*.md`; they render in-app and are submission items.

## Run (wired version)
```bash
python generate_data.py --n 2000 --out data   # builds the synthetic source tables
streamlit run app.py
```
Flow: `customer360.py` (one table) → `exclusion_engine` → `pipeline.py` (propensity) → `carbon_engine` → `grounding.explain`.
