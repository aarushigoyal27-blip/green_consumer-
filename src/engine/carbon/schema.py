"""Output contract for the carbon engine. Every product returns one ImpactResult."""
from dataclasses import dataclass, field, asdict
from typing import Optional

STATUSES = ("ok", "partial", "insufficient_data", "not_applicable")


@dataclass
class ImpactResult:
    product: str
    status: str                                  # one of STATUSES
    headline_metric: Optional[str] = None        # e.g. "kg_co2e_avoided_per_yr", "kg_paper_avoided_per_yr"
    headline_value: Optional[float] = None
    headline_unit: Optional[str] = None
    kg_co2e_avoided_per_yr: Optional[float] = None   # None for GP04: paper is not reported as headline carbon
    baseline_kg_co2e_per_yr: Optional[float] = None
    project_kg_co2e_per_yr: Optional[float] = None
    breakdown: dict = field(default_factory=dict)      # per-fuel / intermediate quantities
    supplementary: dict = field(default_factory=dict)  # separately labelled lines (e.g. paper carbon)
    estimate_quality: Optional[str] = None             # high | medium | low
    horizon: str = "annual"
    method: str = ""
    assumptions: list = field(default_factory=list)
    factor_refs: list = field(default_factory=list)
    missing_fields: list = field(default_factory=list)
    is_estimate: bool = True

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"invalid status {self.status!r}")

    def to_dict(self) -> dict:
        return asdict(self)
