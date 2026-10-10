# PS1 · Green Customer Insights Platform (Megathon X)

Streamlit shell with placeholder pages and documentation templates.

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Layout
```
app.py            navigation (st.navigation)
views/            one file per page – placeholders for now
src/ui.py         shared helpers (banner, doc reader, Mermaid renderer)
docs/             data_card, label_rules, eval_report, responsible_ai_note (.md)
                  architecture.mmd (Mermaid, rendered on the Architecture page)
```

## Wiring real work in
1. Replace mock values in `views/*.py` with calls into `src/` modules.
2. Remove a page's placeholder banner (`header(..., todo=...)`) once it shows real output.
3. Fill `docs/*.md`; they render in-app and are submission items.
