# Archive — superseded files, kept for reference only

Nothing here is imported or tested.

| File | What it was | Why archived |
|------|-------------|--------------|
| `carbon_engine_v0_orphan.py` | First carbon engine (Streamlit shell) | Nothing imported it; replaced by `src/engine/carbon` (YAML assumptions, MGD003 table, tests) |
| `generate_data_12m_alt.py` | Alternative synthetic generator, 12-month lookback, richer schema | Not the pipeline that produced `customer_360.csv`; conflicts with contract feature window (README issue #3) |
| `test_exclusion_engine_v1.py` | Tests for exclusion engine v1 | Targets removed API (`PRODUCT_CATALOGUE_SPECS`); replaced by `tests/acceptance` + `tests/test_exclusion_vocab.py` |
| `green_products_tabbed_v0.csv` | Tab-separated product table | Older copy; `config/green_products.csv` has `opportunity_key` etc. |
| `requirements_streamlit_shell.txt` | Streamlit shell deps | Folded into root `requirements.txt` |
