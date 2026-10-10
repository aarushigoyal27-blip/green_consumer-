"""Pre-submission gate for the carbon engine. Exit code 1 while any placeholder remains.
Usage: python scripts/check_submission_ready.py
"""
import sys
from pathlib import Path

import yaml

root = Path(__file__).resolve().parents[1]
problems = []

data = yaml.safe_load((root / "config/carbon_assumptions.yaml").read_text(encoding="utf-8"))
for key, a in data.items():
    if "VERIFY" in str(a.get("source", "")).upper():
        problems.append(f"assumption {key}: value {a.get('value')} still has a VERIFY source")

csv_text = (root / "config/emission_factors.csv").read_text(encoding="utf-8-sig")
if "FILL" in csv_text:
    problems.append("emission_factors.csv still contains FILL placeholders")

import subprocess
drift = subprocess.run([sys.executable, str(root / "scripts/build_emission_factors.py"), "--check"],
                       capture_output=True, text=True)
if drift.returncode != 0:
    problems.append("emission_factors.csv drifted from config/raw/desnz_extract.csv: "
                    + (drift.stderr or drift.stdout).strip())

mgd = subprocess.run([sys.executable, str(root / "scripts/build_mgd003_table.py"), "--check"],
                     capture_output=True, text=True)
if mgd.returncode != 0:
    problems.append("mcs_mgd003_pv_only.csv drifted from the MGD 003 workbook: "
                    + (mgd.stderr or mgd.stdout).strip())

if problems:
    print("NOT READY:\n  " + "\n  ".join(problems))
    sys.exit(1)
print("Carbon config ready: every assumption cited, no factor placeholders.")
