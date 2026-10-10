"""Propensity input from person B, plus a stub generator in exactly B's format.

Format (CSV): customer_id, opportunity, propensity, confidence, reason_codes
- opportunity: opportunity NAME (EV_FINANCE ...), not GP code
- propensity, confidence: floats in [0, 1]
- reason_codes: pipe-separated, e.g. HIGH_FUEL_SPEND|EXISTING_VEHICLE
"""
import csv
import random
from pathlib import Path

from .opportunities import OPPORTUNITIES

COLUMNS = ["customer_id", "opportunity", "propensity", "confidence", "reason_codes"]


def load_propensities(path) -> dict:
    """-> {(customer_id, opportunity): {"propensity", "confidence", "reason_codes"}}"""
    out = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        for i, row in enumerate(csv.DictReader(fh), start=2):
            opp = row["opportunity"].strip()
            if opp not in OPPORTUNITIES:
                raise ValueError(f"line {i}: unknown opportunity {opp!r} (use names, not GP codes)")
            p, conf = float(row["propensity"]), float(row["confidence"])
            if not (0 <= p <= 1 and 0 <= conf <= 1):
                raise ValueError(f"line {i}: propensity/confidence must be in [0, 1]")
            key = (row["customer_id"].strip(), opp)
            if key in out:
                raise ValueError(f"line {i}: duplicate {key}")
            codes = [c for c in (row.get("reason_codes") or "").split("|") if c]
            out[key] = {"propensity": p, "confidence": conf, "reason_codes": codes}
    return out


def write_stub_propensities(customer_ids, path, seed=42):
    """Random placeholder until B's models exist. NOT a model - never report metrics on it."""
    rng = random.Random(seed)
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        for cid in customer_ids:
            for opp in OPPORTUNITIES:
                w.writerow([cid, opp, round(rng.random(), 3), round(rng.uniform(0.5, 0.95), 3), "STUB"])
