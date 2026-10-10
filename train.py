"""Train the 4 propensity models.   python generate_data.py --n 2000 --out data && python train.py

Writes:  models/<GP>.joblib   models/metrics.json   predictions/test_predictions.csv
Rules: split is by customer (already in customers.csv), fit on TRAIN only, tune/inspect on VAL,
touch TEST once at the end. Only ELIGIBLE customer x product pairs with a label are used.
"""
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

import customer360 as c360
from pipeline import MODEL_FEATURES

OUT = Path(__file__).parent
(OUT / "models").mkdir(exist_ok=True)
(OUT / "predictions").mkdir(exist_ok=True)

t = c360.table().set_index("customer_id")
lab = pd.read_csv(c360.DATA / "takeup_labels.csv")
lab = lab[lab["eligible"] & lab["took_up"].notna()]

metrics, test_rows = {}, []
for gp, feats in MODEL_FEATURES.items():
    d = lab[lab["product_id"] == gp].join(t[feats + ["split"]], on="customer_id")
    tr, va, te = (d[d["split"] == s] for s in ("train", "val", "test"))
    y = lambda x: x["took_up"].astype(int)

    # simple baseline to beat: scaled logistic regression
    base = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=1000))
    base.fit(tr[feats], y(tr))
    model = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, random_state=42)
    model.fit(tr[feats], y(tr))

    f = lambda m, x, fn: float(fn(y(x), m.predict_proba(x[feats])[:, 1]))
    metrics[gp] = {
        "n_train": len(tr), "n_val": len(va), "n_test": len(te), "val_base_rate": float(y(va).mean()),
        "val_pr_auc_baseline": f(base, va, average_precision_score), "val_pr_auc": f(model, va, average_precision_score),
        "val_roc_auc": f(model, va, roc_auc_score), "test_pr_auc": f(model, te, average_precision_score),
    }
    joblib.dump(model, OUT / "models" / f"{gp}.joblib")
    test_rows.append(te[["customer_id"]].assign(product_id=gp, propensity=model.predict_proba(te[feats])[:, 1].round(4)))
    print(gp, {k: round(v, 3) if isinstance(v, float) else v for k, v in metrics[gp].items()})

(OUT / "models" / "metrics.json").write_text(json.dumps(metrics, indent=2))
pd.concat(test_rows).to_csv(OUT / "predictions" / "test_predictions.csv", index=False)
