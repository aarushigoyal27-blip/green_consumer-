"""Product targeting and exclusion rules engine - Lloyds PS1 (Green Customer Insights).

Deterministic rules that decide whether a customer may be TARGETED with a product.
This is marketing suppression, not financial eligibility: under the PS1 core rule,
financial eligibility is decided by the institution's authorised product processes.

Three outcomes per customer x product:
  EXCLUDED           at least one rule rules the product out (codes say which, truthfully)
  INSUFFICIENT_DATA  no rule excludes, but a field a rule needs is missing (listed in missing_fields)
  QUALIFIED          every applicable rule has its data and none excludes

Missing data is never treated as a negative fact (unknown tenure is not "tenant").
Product numbering follows the PS1 spec, Section 2: GP01 EV, GP02 Green Home, GP03 Solar, GP04 Paperless.
Unknown categorical values raise UnknownVocabularyError (call validate_records() at load time).
Contract: contract.json v2.1 (single_product_decision_output).
"""
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

# --------------------------------------------------------------------------- windows
OBSERVATION_WINDOW_START = "2026-01-01"
OBSERVATION_WINDOW_END = "2026-06-30"
CUTOFF_DATE = "2026-06-30"
OUTCOME_WINDOW_START = "2026-07-01"
OUTCOME_WINDOW_END = "2026-12-31"


# --------------------------------------------------------------------------- products
class ProductCode(str, Enum):
    GP01 = "GP01"
    GP02 = "GP02"
    GP03 = "GP03"
    GP04 = "GP04"


class OpportunityKey(str, Enum):
    EV_FINANCE = "EV_FINANCE"
    GREEN_HOME = "GREEN_HOME"
    SOLAR_FINANCE = "SOLAR_FINANCE"
    PAPERLESS_BANKING = "PAPERLESS_BANKING"


PRODUCT_TO_OPPORTUNITY = {  # PS1 spec Section 2 / green_products.csv
    ProductCode.GP01: OpportunityKey.EV_FINANCE,
    ProductCode.GP02: OpportunityKey.GREEN_HOME,
    ProductCode.GP03: OpportunityKey.SOLAR_FINANCE,
    ProductCode.GP04: OpportunityKey.PAPERLESS_BANKING,
}
OPPORTUNITY_TO_PRODUCT = {v: k for k, v in PRODUCT_TO_OPPORTUNITY.items()}

PRODUCT_NAMES = {
    ProductCode.GP01: "EV Finance",
    ProductCode.GP02: "Green Home Loan",
    ProductCode.GP03: "Solar Finance",
    ProductCode.GP04: "Paperless Banking",
}

CREDIT_PRODUCTS = {ProductCode.GP01, ProductCode.GP02, ProductCode.GP03}
HOME_PRODUCTS = {ProductCode.GP02, ProductCode.GP03}


# --------------------------------------------------------------------------- statuses / codes
class TargetingStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    EXCLUDED = "EXCLUDED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ExclusionReasonCode(str, Enum):
    # universal
    EXC_OPT_OUT = "EXC_OPT_OUT"
    EXC_COMPLIANCE_HOLD = "EXC_COMPLIANCE_HOLD"
    EXC_REGIONAL_RESTRICTION = "EXC_REGIONAL_RESTRICTION"
    EXC_AGE_RESTRICTION = "EXC_AGE_RESTRICTION"
    EXC_INACTIVE_ACCOUNT = "EXC_INACTIVE_ACCOUNT"
    EXC_DUPLICATE_OFFER = "EXC_DUPLICATE_OFFER"
    # credit products (GP01-GP03)
    EXC_ARREARS_OR_DEFAULT = "EXC_ARREARS_OR_DEFAULT"
    # home products (GP02, GP03)
    EXC_NOT_HOMEOWNER = "EXC_NOT_HOMEOWNER"
    # product-specific
    EXC_ALREADY_EV_OWNER = "EXC_ALREADY_EV_OWNER"
    EXC_NO_VEHICLE = "EXC_NO_VEHICLE"
    EXC_PROPERTY_MAX_EFFICIENCY = "EXC_PROPERTY_MAX_EFFICIENCY"
    EXC_PROPERTY_TYPE_INELIGIBLE = "EXC_PROPERTY_TYPE_INELIGIBLE"
    EXC_ALREADY_SOLAR_INSTALLED = "EXC_ALREADY_SOLAR_INSTALLED"
    EXC_ALREADY_PAPERLESS = "EXC_ALREADY_PAPERLESS"
    EXC_NO_DIGITAL_CHANNEL = "EXC_NO_DIGITAL_CHANNEL"


E = ExclusionReasonCode

# --------------------------------------------------------------------------- helpers
def _upper(v) -> Optional[str]:
    return None if v is None else str(v).strip().upper()


def _is_missing(v) -> bool:
    return v is None or (isinstance(v, float) and v != v)  # None or NaN (pandas)


# --------------------------------------------------------------------------- vocabulary
# Every categorical value a rule reads must be listed here. Anything else raises
# UnknownVocabularyError, so vocabulary drift between the data generator, this engine and
# contract.json fails at load time instead of silently passing a rule.
# tests/test_exclusion_vocab.py asserts these sets match the enums in contract.json.
OWNER_STATUSES = {"OWNER", "OWNER_OCCUPIER", "MORTGAGED"}
NON_OWNER_STATUSES = {"TENANT", "LODGER", "COUNCIL_TENANT"}
UNKNOWN_TENURE_STATUSES = {"UNKNOWN"}                       # explicit "don't know" -> INSUFFICIENT_DATA
NO_ROOF_PROPERTY_TYPES = {"FLAT", "APARTMENT", "MAISONETTE_SHARED", "COMMUNAL"}
HOUSE_PROPERTY_TYPES = {"DETACHED", "SEMI_DETACHED", "TERRACED", "BUNGALOW"}
ACTIVE_ACCOUNT_STATUSES = {"ACTIVE"}
INACTIVE_ACCOUNT_STATUSES = {"DORMANT", "CLOSED", "BLOCKED", "FROZEN"}
CLEAR_COMPLIANCE_STATUSES = {"CLEAR"}
HOLD_COMPLIANCE_STATUSES = {"HOLD", "INVESTIGATION", "SANCTION"}
GOOD_STANDING_DELINQUENCY = {"CURRENT"}
ARREARS_DELINQUENCY = {"30_DAYS", "60_DAYS", "90_DAYS", "ARREARS", "DEFAULT"}  # any missed payment
EPC_RATINGS = {"A", "B", "C", "D", "E", "F", "G"}
# vehicle_fuel_type is not used by any rule, but it is passed to the LLM, so it is normalised
# to the contract's lowercase values. Aliases are explicit; nothing else is accepted.
VEHICLE_FUEL_TYPES = {"petrol", "diesel", "hybrid", "ev"}
VEHICLE_FUEL_ALIASES = {"ELECTRIC": "ev", "BEV": "ev"}
UK_COUNTRY_CODES = {"GB", "UK"}      # country_code is open-ended: any other code is a valid non-UK value

VOCABULARY: Dict[str, set] = {
    "homeowner_status": OWNER_STATUSES | NON_OWNER_STATUSES | UNKNOWN_TENURE_STATUSES,
    "property_type": HOUSE_PROPERTY_TYPES | NO_ROOF_PROPERTY_TYPES,
    "account_status": ACTIVE_ACCOUNT_STATUSES | INACTIVE_ACCOUNT_STATUSES,
    "compliance_status": CLEAR_COMPLIANCE_STATUSES | HOLD_COMPLIANCE_STATUSES,
    "delinquency_status": GOOD_STANDING_DELINQUENCY | ARREARS_DELINQUENCY,
    "property_epc_rating": EPC_RATINGS,
    "vehicle_fuel_type": {v.upper() for v in VEHICLE_FUEL_TYPES} | set(VEHICLE_FUEL_ALIASES),
}


class UnknownVocabularyError(ValueError):
    """A categorical field holds a value the rules do not know how to interpret."""

    def __init__(self, problems: Dict[str, Dict[str, int]]):
        self.problems = problems  # {field: {unknown_value: count}}
        lines = [f"  {f}: {', '.join(f'{v!r} x{n}' for v, n in sorted(vals.items()))} "
                 f"(allowed: {', '.join(sorted(VOCABULARY[f]))})" for f, vals in sorted(problems.items())]
        super().__init__("Unknown categorical values; add them to VOCABULARY and contract.json "
                         "or fix the data:\n" + "\n".join(lines))


def _unknown_values(record: Dict[str, Any]) -> Dict[str, str]:
    out = {}
    for f, allowed in VOCABULARY.items():
        v = record.get(f)
        if not _is_missing(v) and _upper(v) not in allowed:
            out[f] = str(v)
    return out


def validate_records(records: Iterable[Dict[str, Any]]) -> int:
    """Load-time check. Scans every record and raises ONE error listing all unknown values
    with counts. Accepts a list of dicts or a pandas DataFrame. Returns the number checked."""
    if hasattr(records, "to_dict"):           # pandas DataFrame, without importing pandas
        records = records.to_dict("records")
    problems: Dict[str, Dict[str, int]] = {}
    n = 0
    for n, rec in enumerate(records, 1):
        for f, v in _unknown_values(rec).items():
            problems.setdefault(f, {}).setdefault(v, 0)
            problems[f][v] += 1
    if problems:
        raise UnknownVocabularyError(problems)
    return n


def _normalise_fuel_type(v) -> Optional[str]:
    if _is_missing(v):
        return None
    u = _upper(v)
    return VEHICLE_FUEL_ALIASES.get(u, u.lower())


COOLING_OFF_DAYS = 90
MIN_AGE = 18


# --------------------------------------------------------------------------- output
@dataclass
class TargetingDecision:
    customer_id: str
    product_code: str
    opportunity: str
    product_name: str
    cutoff_date: str
    targetable: bool
    targeting_status: str
    exclusion_reason_codes: List[str]
    missing_fields: List[str]
    requires_human_review: bool
    propensity: Optional[float] = None          # filled by the ML layer, never here
    confidence: Optional[float] = None
    reason_codes: List[str] = field(default_factory=list)
    impact: Optional[Dict[str, Any]] = None     # filled by the carbon engine, never here
    grounded_attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# Observed inputs passed through for explanation. No modelled numbers (carbon, value) here.
GROUNDED_INPUT_FIELDS = ("annual_fuel_spend", "annual_mileage_km", "baseline_electricity_kwh",
                         "baseline_gas_kwh", "paper_statements_per_year", "property_epc_rating",
                         "property_type", "vehicle_fuel_type")


class _Rules:
    """Collects exclusions and missing fields while rules run."""

    def __init__(self, customer: Dict[str, Any]):
        bad = _unknown_values(customer)
        if bad:
            raise UnknownVocabularyError({f: {v: 1} for f, v in bad.items()})
        self.c = {k: (None if _is_missing(v) else v) for k, v in customer.items()}
        self.codes: List[str] = []
        self.missing: List[str] = []

    def get(self, key):
        return self.c.get(key)

    def exclude(self, code: ExclusionReasonCode):
        if code.value not in self.codes:
            self.codes.append(code.value)

    def need(self, *keys) -> bool:
        """Record any missing keys; True only if all are present."""
        ok = True
        for k in keys:
            if self.c.get(k) is None:
                ok = False
                if k not in self.missing:
                    self.missing.append(k)
        return ok


# --------------------------------------------------------------------------- engine
class ExclusionEngine:

    @staticmethod
    def resolve_product(product_ref: Any) -> ProductCode:
        """Accepts a spec GP code or an opportunity name. Nothing else."""
        if isinstance(product_ref, ProductCode):
            return product_ref
        if isinstance(product_ref, OpportunityKey):
            return OPPORTUNITY_TO_PRODUCT[product_ref]
        key = str(product_ref).strip().upper()
        if key in ProductCode.__members__:
            return ProductCode(key)
        if key in OpportunityKey.__members__:
            return OPPORTUNITY_TO_PRODUCT[OpportunityKey(key)]
        raise ValueError(f"Unknown product reference: {product_ref!r}")

    # ---- universal rules (all products)
    @staticmethod
    def _universal(r: _Rules, product: ProductCode):
        if r.need("marketing_consent") and r.get("marketing_consent") is False:
            r.exclude(E.EXC_OPT_OUT)            # PECR: unknown consent is not consent -> insufficient

        if r.need("compliance_status") and _upper(r.get("compliance_status")) in HOLD_COMPLIANCE_STATUSES:
            r.exclude(E.EXC_COMPLIANCE_HOLD)

        uk, country = r.get("uk_resident"), _upper(r.get("country_code"))
        if uk is False or (country is not None and country not in UK_COUNTRY_CODES):
            r.exclude(E.EXC_REGIONAL_RESTRICTION)
        elif uk is None and country is None:
            r.need("uk_resident")

        if r.need("age") and r.get("age") < MIN_AGE:
            r.exclude(E.EXC_AGE_RESTRICTION)     # no upper age limit (age discrimination risk)

        acct, txns = _upper(r.get("account_status")), r.get("transaction_count_6m")
        if acct in INACTIVE_ACCOUNT_STATUSES or txns == 0:
            r.exclude(E.EXC_INACTIVE_ACCOUNT)
        elif acct is None:
            r.need("account_status")

        days = r.get("days_since_last_offer_decline")
        if days is not None and days < COOLING_OFF_DAYS:   # explicit None check: 0 days must exclude
            r.exclude(E.EXC_DUPLICATE_OFFER)

        if product in CREDIT_PRODUCTS:
            delinquency = _upper(r.get("delinquency_status"))
            if r.get("is_in_arrears") is True or delinquency in ARREARS_DELINQUENCY:
                r.exclude(E.EXC_ARREARS_OR_DEFAULT)
            elif r.get("is_in_arrears") is None and delinquency is None:
                r.need("is_in_arrears")

    # ---- product rules
    @staticmethod
    def _ev(r: _Rules):
        if r.need("is_ev_owner") and r.get("is_ev_owner") is True:
            # FR7: exclude only when no replacement use case remains (no petrol/diesel car)
            if r.need("has_ice_vehicle") and r.get("has_ice_vehicle") is False:
                r.exclude(E.EXC_ALREADY_EV_OWNER)
        has_vehicle = r.get("has_vehicle")
        usage = any((r.get(k) or 0) > 0 for k in ("annual_fuel_spend", "annual_mileage_km"))
        if has_vehicle is False and not usage:
            r.exclude(E.EXC_NO_VEHICLE)
        elif has_vehicle is None and not usage and r.get("has_ice_vehicle") is not True:
            r.need("has_vehicle")

    @staticmethod
    def _tenure(r: _Rules):
        tenure = _upper(r.get("homeowner_status"))
        if tenure in NON_OWNER_STATUSES:
            r.exclude(E.EXC_NOT_HOMEOWNER)
        elif tenure is None or tenure in UNKNOWN_TENURE_STATUSES:
            if "homeowner_status" not in r.missing:
                r.missing.append("homeowner_status")

    @classmethod
    def _green_home(cls, r: _Rules):
        cls._tenure(r)
        if _upper(r.get("property_epc_rating")) in ("A", "B"):
            r.exclude(E.EXC_PROPERTY_MAX_EFFICIENCY)
        # EPC missing is fine: a retrofit can still be relevant without a certificate

    @classmethod
    def _solar(cls, r: _Rules):
        cls._tenure(r)
        ptype = _upper(r.get("property_type"))
        if ptype in NO_ROOF_PROPERTY_TYPES:
            r.exclude(E.EXC_PROPERTY_TYPE_INELIGIBLE)
        elif ptype not in HOUSE_PROPERTY_TYPES:
            r.need("property_type")
        if r.need("has_solar") and r.get("has_solar") is True:
            r.exclude(E.EXC_ALREADY_SOLAR_INSTALLED)

    @staticmethod
    def _paperless(r: _Rules):
        if r.need("is_paperless") and r.get("is_paperless") is True:
            r.exclude(E.EXC_ALREADY_PAPERLESS)
        if r.get("has_digital_banking") is False or r.get("digital_logins_90d") == 0:
            r.exclude(E.EXC_NO_DIGITAL_CHANNEL)
        elif r.get("has_digital_banking") is None:
            r.need("has_digital_banking")

    @classmethod
    def evaluate(cls, customer: Dict[str, Any], product_ref: Any,
                 cutoff_date: str = CUTOFF_DATE) -> TargetingDecision:
        product = cls.resolve_product(product_ref)
        r = _Rules(customer or {})
        cls._universal(r, product)
        {ProductCode.GP01: cls._ev, ProductCode.GP02: cls._green_home,
         ProductCode.GP03: cls._solar, ProductCode.GP04: cls._paperless}[product](r)

        if r.codes:
            status = TargetingStatus.EXCLUDED
        elif r.missing:
            status = TargetingStatus.INSUFFICIENT_DATA
        else:
            status = TargetingStatus.QUALIFIED

        vulnerable = r.get("vulnerability_flag") is True
        grounded = {"data_cutoff_date": r.get("data_cutoff_date") or cutoff_date}
        grounded.update({k: r.get(k) for k in GROUNDED_INPUT_FIELDS})
        grounded["vehicle_fuel_type"] = _normalise_fuel_type(r.get("vehicle_fuel_type"))

        return TargetingDecision(
            customer_id=str(r.get("customer_id") or "UNKNOWN"),
            product_code=product.value,
            opportunity=PRODUCT_TO_OPPORTUNITY[product].value,
            product_name=PRODUCT_NAMES[product],
            cutoff_date=cutoff_date,
            targetable=status == TargetingStatus.QUALIFIED,
            targeting_status=status.value,
            exclusion_reason_codes=sorted(r.codes),
            missing_fields=sorted(r.missing),
            requires_human_review=vulnerable,   # Consumer Duty: extra care, not exclusion
            grounded_attributes=grounded,
        )


def evaluate_customer_targeting(customer_profile: Dict[str, Any], product_code: Any,
                                cutoff_date: str = CUTOFF_DATE) -> Dict[str, Any]:
    """Public entry point. Returns a dict conforming to contract.json single_product_decision_output."""
    return ExclusionEngine.evaluate(customer_profile, product_code, cutoff_date).to_dict()


def evaluate_all_products(customer_profile: Dict[str, Any], cutoff_date: str = CUTOFF_DATE) -> Dict[str, Any]:
    return {p.value: evaluate_customer_targeting(customer_profile, p, cutoff_date) for p in ProductCode}