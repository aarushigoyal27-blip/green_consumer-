"""Build config/emission_factors.csv from the DESNZ extract (config/raw/desnz_extract.csv).

Reproducible selection: each engine activity key is matched to exactly one extract row
by (original activity, unit, DESNZ row label). A missing or ambiguous match fails loudly.
Usage: python scripts/build_emission_factors.py [--check]
  --check  compare with the existing config file instead of writing it (exit 1 on drift)
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "config/raw/desnz_extract.csv"
OUT = ROOT / "config/emission_factors.csv"

# engine key -> (original activity, unit, source_row_label), with the note kept in the output
SELECTION = {
    "electricity_generation_kwh": ("Grid electricity", "kWh", "Electricity: UK", ""),
    "electricity_td_kwh": ("Electricity transmission and distribution losses", "kWh", "Electricity: UK",
                           "Add to generation for a consumer view"),
    "natural_gas_gross_cv_kwh": ("Natural gas", "kWh", "Natural gas (Gross CV)", "UK gas bills are in gross-CV kWh"),
    "petrol_car_avg_km": ("Petrol car average", "km", "Average car: Petrol", ""),
    "diesel_car_avg_km": ("Diesel car average", "km", "Average car: Diesel", ""),
    "petrol_litre": ("Petrol", "litres", "Petrol", "Converts fuel spend → litres → CO2e"),
    "diesel_litre": ("Diesel", "litres", "Diesel (average biofuel blend)", "Converts fuel spend → litres → CO2e"),
    "paper_primary_tonne": ("Paper (primary production)", "tonnes", "Paper",
                            "Usually per tonne; convert per statement with a stated grams assumption"),
}
# DESNZ 2026 BEV per-km rows could not be downloaded, and the extract's single BEV row
# (0.06012/km) implied 0.42 kWh/km, about double a real BEV. The BEV factors are therefore
# derived the way DESNZ builds them (methodology report 2026, Tables 18/20: real-world Wh/km x
# UK electricity generation and T&D factors), using a published average-car energy use.
BEV_KWH_PER_KM = 0.2171
BEV_KWH_SOURCE = ("Energy Saving Trust Fleet Decarbonisation Toolkit 1.3, Table 6 'Average electric car' "
                  "0.2171 kWh/km (based on DESNZ 2025 conversion factors)")
DERIVED = {
    "bev_avg_km": ("electricity_generation_kwh", 2, "Generation component"),
    "bev_td_avg_km": ("electricity_td_kwh", 3, "T&D component"),
}

COLUMNS = ["activity", "unit", "kg_co2e_per_unit", "scope", "factor_year",
           "source_sheet", "source_row_label", "notes"]


def build():
    rows = list(csv.DictReader(RAW.open(newline="", encoding="utf-8-sig")))
    out = []
    for key, (act, unit, label, note) in SELECTION.items():
        hits = [r for r in rows if r["activity"].strip() == act and r["unit"].strip() == unit
                and r["source_row_label"].strip() == label]
        if len(hits) != 1:
            sys.exit(f"{key}: expected 1 match for ({act}, {unit}, {label}), found {len(hits)}")
        r = hits[0]
        notes = " | ".join(x for x in (note, f"original activity: {act}") if x)
        out.append([key, r["unit"], r["kg_co2e_per_unit"], r["scope"], r["factor_year"],
                    r["source_sheet"], r["source_row_label"], notes])
    by_key = {row[0]: row for row in out}
    for key, (elec_key, scope, part) in DERIVED.items():
        elec = by_key[elec_key]
        value = round(BEV_KWH_PER_KM * float(elec[2]), 6)
        out.append([key, "km", f"{value}", scope, elec[4],
                    f"Derived: {BEV_KWH_PER_KM} kWh/km x {elec[5]}", elec[6],
                    f"{part} | {BEV_KWH_PER_KM} kWh/km x {elec[2]} kg/kWh | kWh/km source: {BEV_KWH_SOURCE}"])
    return out


def _values(path):
    return {r["activity"]: float(r["kg_co2e_per_unit"])
            for r in csv.DictReader(path.open(newline="", encoding="utf-8-sig"))}


if __name__ == "__main__":
    rows = build()
    if "--check" in sys.argv:
        built = {r[0]: float(r[2]) for r in rows}
        drift = {k: (v, built.get(k)) for k, v in _values(OUT).items() if built.get(k) != v}
        if drift:
            sys.exit(f"config/emission_factors.csv differs from extract: {drift}")
        print("config/emission_factors.csv matches the DESNZ extract.")
    else:
        with OUT.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(COLUMNS)
            w.writerows(rows)
        print(f"wrote {OUT.relative_to(ROOT)} ({len(rows)} factors)")
