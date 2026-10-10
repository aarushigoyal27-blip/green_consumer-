"""Per-opportunity recommendation thresholds, chosen on the VALIDATION split only.

Rule: recommend the top `top_share` of eligible validation customers per opportunity
(a stand-in for relationship-team contact capacity). threshold = k-th highest validation
propensity, k = ceil(top_share * n). Written to artifacts so the test split never influences it.
"""
import json
import math
from collections import defaultdict
from pathlib import Path


def choose_thresholds(validation_rows, top_share=0.15) -> dict:
    """validation_rows: iterable of (opportunity, propensity) for ELIGIBLE validation customers."""
    if not 0 < top_share <= 1:
        raise ValueError("top_share must be in (0, 1]")
    by_opp = defaultdict(list)
    for opp, p in validation_rows:
        by_opp[opp].append(p)
    out = {}
    for opp, ps in by_opp.items():
        ps.sort(reverse=True)
        k = max(1, math.ceil(top_share * len(ps)))
        out[opp] = ps[k - 1]
    return out


def save_thresholds(thresholds: dict, path, top_share: float, split="validation"):
    Path(path).write_text(json.dumps({"chosen_on": split, "top_share": top_share,
                                      "thresholds": thresholds}, indent=2))


def load_thresholds(path) -> dict:
    data = json.loads(Path(path).read_text())
    if data.get("chosen_on") != "validation":
        raise ValueError("thresholds must be chosen on the validation split")
    return data["thresholds"]
