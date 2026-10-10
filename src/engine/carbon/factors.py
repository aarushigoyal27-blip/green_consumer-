"""Load and validate emission factors (DESNZ) and modelling assumptions.

The engine never contains a factor value in code. Every number comes from
config/emission_factors.csv or config/carbon_assumptions.yaml, so judges can
trace each figure to a sheet + row label or a cited source.
"""
import csv
from dataclasses import dataclass
from pathlib import Path

import yaml

# activity key -> expected (normalised) unit of the denominator
REQUIRED_ACTIVITIES = {
    "electricity_generation_kwh": "kwh",
    "electricity_td_kwh": "kwh",
    "natural_gas_gross_cv_kwh": "kwh",
    "petrol_car_avg_km": "km",
    "diesel_car_avg_km": "km",
    "bev_avg_km": "km",
    "bev_td_avg_km": "km",
    "petrol_litre": "litre",
    "diesel_litre": "litre",
    "paper_primary_tonne": "tonne",
}

_UNIT_ALIASES = {
    "kwh": "kwh", "kwh (gross cv)": "kwh", "kwh (gross)": "kwh",
    "km": "km", "kilometre": "km", "kilometres": "km",
    "litre": "litre", "litres": "litre", "l": "litre",
    "tonne": "tonne", "tonnes": "tonne", "t": "tonne",
}

REQUIRED_ASSUMPTIONS = [
    "electricity_include_td",
    "gp01_pump_price_petrol", "gp01_pump_price_diesel", "gp01_unknown_fuel_default",
    "gp03_system_kwp", "gp03_yield_kwh_per_kwp",
    "gp02_reduction_share_electricity", "gp02_reduction_share_gas",
    "gp04_pages_per_statement", "gp04_grams_per_page", "gp04_report_paper_carbon",
]


class ConfigError(ValueError):
    pass


def _norm_unit(u: str) -> str:
    return _UNIT_ALIASES.get(u.strip().lower(), u.strip().lower())


@dataclass(frozen=True)
class Factor:
    activity: str
    unit: str
    kg_co2e_per_unit: float
    factor_year: str
    source_sheet: str
    source_row_label: str

    def ref(self) -> dict:
        return {
            "activity": self.activity,
            "kg_co2e_per_unit": self.kg_co2e_per_unit,
            "unit": self.unit,
            "factor_year": self.factor_year,
            "source_sheet": self.source_sheet,
            "source_row_label": self.source_row_label,
        }


class FactorTable:
    def __init__(self, factors: dict):
        self._f = factors

    def get(self, activity: str) -> Factor:
        try:
            return self._f[activity]
        except KeyError:
            raise ConfigError(f"emission factor '{activity}' not found") from None

    def electricity(self, include_td: bool):
        """Consumer-side grid factor: generation (+ T&D losses if configured)."""
        gen = self.get("electricity_generation_kwh")
        if not include_td:
            return gen.kg_co2e_per_unit, [gen.ref()]
        td = self.get("electricity_td_kwh")
        return gen.kg_co2e_per_unit + td.kg_co2e_per_unit, [gen.ref(), td.ref()]


def _bev(self, include_td: bool):
    """BEV per-km factor on the same basis as household electricity: generation
    (+ T&D losses if configured), so the EV comparison follows electricity_include_td."""
    gen = self.get("bev_avg_km")
    if not include_td:
        return gen.kg_co2e_per_unit, [gen.ref()]
    td = self.get("bev_td_avg_km")
    return gen.kg_co2e_per_unit + td.kg_co2e_per_unit, [gen.ref(), td.ref()]


FactorTable.bev = _bev


def load_factors(path) -> FactorTable:
    path = Path(path)
    factors = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for i, row in enumerate(csv.DictReader(fh), start=2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            act = row.get("activity", "")
            if not act or act.startswith("#"):
                continue
            if act in factors:
                raise ConfigError(f"{path.name} line {i}: duplicate activity '{act}'")
            try:
                val = float(row["kg_co2e_per_unit"])
            except (KeyError, ValueError):
                raise ConfigError(f"{path.name} line {i}: kg_co2e_per_unit is not a number") from None
            if val <= 0:
                raise ConfigError(f"{path.name} line {i}: factor for '{act}' must be > 0")
            for col in ("unit", "source_sheet", "source_row_label"):
                if not row.get(col):
                    raise ConfigError(f"{path.name} line {i}: '{act}' is missing {col}")
            factors[act] = Factor(act, row["unit"], val, row.get("factor_year", ""),
                                  row["source_sheet"], row["source_row_label"])

    missing = [a for a in REQUIRED_ACTIVITIES if a not in factors]
    if missing:
        raise ConfigError(f"{path.name} is missing required activities: {missing}")
    for act, expected in REQUIRED_ACTIVITIES.items():
        got = _norm_unit(factors[act].unit)
        if got != expected:
            raise ConfigError(f"'{act}' has unit '{factors[act].unit}', expected per {expected} "
                              f"(per-mile or net-CV rows are a common copy error)")
    return FactorTable(factors)


class SelfConsumptionTable:
    """MCS MGD 003 'PV Only' self-consumption shares, keyed by occupancy archetype,
    annual consumption band and annual generation band (config/mcs_mgd003_pv_only.csv).
    MGD 003 is only defined for consumption 1,500-5,999 kWh and generation < 6,000 kWh;
    outside that range the nearest band is used and the result is flagged."""

    def __init__(self, rows: list):
        self._rows = rows
        self.archetypes = sorted({r["archetype"] for r in rows})

    def lookup(self, archetype: str, consumption_kwh: float, generation_kwh: float):
        rows = [r for r in self._rows if r["archetype"] == archetype]
        if not rows:
            raise ConfigError(f"unknown MGD 003 archetype {archetype!r}; options: {self.archetypes}")
        c_lo = min(r["c_min"] for r in rows)
        c_hi = max(r["c_max"] for r in rows) + 1
        g_hi = max(r["g_max"] for r in rows) + 1
        in_range = c_lo <= consumption_kwh < c_hi and generation_kwh < g_hi
        c = min(max(consumption_kwh, c_lo), c_hi - 1)
        g = min(max(generation_kwh, 0), g_hi - 1)
        for r in rows:  # bands are contiguous integer ranges; compare on the floor
            if r["c_min"] <= int(c) <= r["c_max"] and r["g_min"] <= int(g) <= r["g_max"]:
                return r["share"], in_range, r
        raise ConfigError(f"no MGD 003 band for consumption={c}, generation={g}")


def load_self_consumption_table(path) -> SelfConsumptionTable:
    rows = []
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            share = float(r["self_consumption_share"])
            if not 0 <= share <= 1:
                raise ConfigError(f"{Path(path).name}: share {share} outside 0-1")
            rows.append({"archetype": r["archetype"], "c_min": int(r["consumption_kwh_min"]),
                         "c_max": int(r["consumption_kwh_max"]), "g_min": int(r["generation_kwh_min"]),
                         "g_max": int(r["generation_kwh_max"]), "share": share})
    if not rows:
        raise ConfigError(f"{Path(path).name} is empty")
    return SelfConsumptionTable(rows)


class Assumptions:
    def __init__(self, data: dict, self_consumption_table=None):
        self._a = data
        self.self_consumption_table = self_consumption_table

    def has(self, key) -> bool:
        return key in self._a

    def value(self, key):
        return self._a[key]["value"]

    def describe(self, key) -> str:
        a = self._a[key]
        unit = f" {a['unit']}" if a.get("unit") else ""
        return f"{a.get('label', key)}: {a['value']}{unit} (source: {a.get('source', 'not stated')})"


def load_assumptions(path) -> Assumptions:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    missing = [k for k in REQUIRED_ASSUMPTIONS if k not in data]
    if missing:
        raise ConfigError(f"assumptions file missing keys: {missing}")
    for k, v in data.items():
        if not isinstance(v, dict) or "value" not in v:
            raise ConfigError(f"assumption '{k}' must be a mapping with a 'value'")
    table = None
    method = data.get("gp03_self_consumption_method", {}).get("value", "flat")
    if method == "mcs_mgd003":
        for k in ("gp03_occupancy_archetype", "gp03_mgd003_table"):
            if k not in data:
                raise ConfigError(f"gp03_self_consumption_method=mcs_mgd003 needs '{k}'")
        table = load_self_consumption_table(Path(path).parent / data["gp03_mgd003_table"]["value"])
        table.lookup(data["gp03_occupancy_archetype"]["value"], 3000, 3000)  # fail fast on bad archetype
    elif method == "flat":
        if "gp03_self_consumption_share" not in data:
            raise ConfigError("gp03_self_consumption_method=flat needs 'gp03_self_consumption_share'")
    else:
        raise ConfigError(f"gp03_self_consumption_method must be mcs_mgd003 or flat, got {method!r}")
    return Assumptions(data, table)
