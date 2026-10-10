"""Adapter between the recommendation engine and whichever exclusion engine exists.

The recommendation engine only ever calls  adapter(customer, opportunity) -> ExclusionResult.
- StubExclusionAdapter: the three must-have rules, for building/testing now.
- EngineExclusionAdapter: wraps the team's exclusion_engine.evaluate_customer_targeting.
  It passes the OPPORTUNITY NAME (the engine resolves names), so GP numbering never leaks in.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

ELIGIBLE, EXCLUDED, INSUFFICIENT = "eligible", "excluded", "insufficient_data"
OWNER_STATUSES = {"OWNER", "OWNER_OCCUPIER", "MORTGAGED"}
NON_OWNER_STATUSES = {"TENANT", "LODGER", "COUNCIL_TENANT"}


@dataclass
class ExclusionResult:
    status: str                                 # eligible | excluded | insufficient_data
    codes: list = field(default_factory=list)   # exclusion reason codes
    missing_fields: list = field(default_factory=list)
    source: str = "stub"


class StubExclusionAdapter:
    """Must-have rules only (Step 5c). Missing input -> insufficient_data, never a guess."""

    def __call__(self, customer: dict, opportunity: str) -> ExclusionResult:
        c = customer.get
        if opportunity == "EV_FINANCE":
            if c("is_ev_owner") is None:
                return ExclusionResult(INSUFFICIENT, missing_fields=["is_ev_owner"])
            # FR7: exclude only when there is no replacement use case (no petrol/diesel car left)
            if c("is_ev_owner") and not c("has_ice_vehicle"):
                return ExclusionResult(EXCLUDED, ["EXC_ALREADY_EV_OWNER"])
            return ExclusionResult(ELIGIBLE)
        if opportunity in ("GREEN_HOME", "SOLAR_FINANCE"):
            tenure = (c("homeowner_status") or "").upper()
            if tenure in NON_OWNER_STATUSES:
                return ExclusionResult(EXCLUDED, ["EXC_NOT_HOMEOWNER"])
            if tenure not in OWNER_STATUSES:
                return ExclusionResult(INSUFFICIENT, missing_fields=["homeowner_status"])
            return ExclusionResult(ELIGIBLE)
        if opportunity == "PAPERLESS_BANKING":
            if c("is_paperless") is None:
                return ExclusionResult(INSUFFICIENT, missing_fields=["is_paperless"])
            if c("is_paperless"):
                return ExclusionResult(EXCLUDED, ["EXC_ALREADY_PAPERLESS"])
            return ExclusionResult(ELIGIBLE)
        raise ValueError(f"unknown opportunity {opportunity!r}")


class EngineExclusionAdapter:
    """Wraps evaluate_customer_targeting(profile, product_ref) from exclusion_engine.py."""

    STATUS_MAP = {"QUALIFIED": ELIGIBLE, "EXCLUDED": EXCLUDED, "INSUFFICIENT_DATA": INSUFFICIENT}

    def __init__(self, evaluate_fn: Optional[Callable] = None):
        if evaluate_fn is None:
            from exclusion_engine import evaluate_customer_targeting as evaluate_fn  # team's module
        self._eval = evaluate_fn

    def __call__(self, customer: dict, opportunity: str) -> ExclusionResult:
        out = self._eval(customer, opportunity)
        if out.get("opportunity") not in (None, opportunity):
            raise ValueError(f"exclusion engine resolved {opportunity} to {out.get('opportunity')}")
        status = self.STATUS_MAP.get(out.get("targeting_status"))
        if status is None:
            raise ValueError(f"unexpected targeting_status {out.get('targeting_status')!r}")
        return ExclusionResult(status, list(out.get("exclusion_reason_codes") or []),
                               list(out.get("missing_fields") or []), source="exclusion_engine")
