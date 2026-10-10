"""Run explain() + validate() over every row of a factor CSV (default: the raw DESNZ extract).
Usage: python scripts/grounding_csv_demo.py [path/to/file.csv]
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from grounding import explain, validate  # noqa: E402

def run_csv_pipeline(csv_filepath):
    # Open and read the CSV file
    with open(csv_filepath, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row_num, row in enumerate(reader, start=1):
            print(f"\n{'='*40}\nProcessing Row {row_num}\n{'='*40}")
            
            # 1. Convert CSV string values into the correct data types
            # (The validate function relies on numbers being floats/ints to expand candidates correctly)
           # 1. Convert CSV string values into the correct data types
            payload = {
                "activity": row.get("activity"),
                "unit": row.get("unit"),
                "kg_co2e_per_unit": float(row["kg_co2e_per_unit"]) if row.get("kg_co2e_per_unit") else None,
                "scope": int(row["scope"]) if row.get("scope") else None,
                "factor_year": int(row["factor_year"]) if row.get("factor_year") else None,
                "source_sheet": row.get("source_sheet"),
                "source_row_label": row.get("source_row_label"),
                "notes": row.get("notes") or None
            }
            
            # Print the formatted payload
            print("[Input Payload]:")
            print(json.dumps(payload, indent=2))
            
            # 2. Run the explain() function
            print("\n[Generated Explanation]:")
            grounded_text = explain(payload)
            print(grounded_text)
            
            # 3. Run the validate() function
            print("\n[Validation Results]:")
            errors = validate(grounded_text, payload)
            
            if not errors:
                print(">> STATUS: PASS (0 unsupported numbers)")
            else:
                print(f">> STATUS: FAIL ({len(errors)} unsupported numbers detected)")
                for err in errors:
                    print(f"   - Invalid Token: '{err.raw}'")

if __name__ == "__main__":
    default_csv = ROOT / "config" / "raw" / "desnz_extract.csv"
    run_csv_pipeline(sys.argv[1] if len(sys.argv) > 1 else default_csv)