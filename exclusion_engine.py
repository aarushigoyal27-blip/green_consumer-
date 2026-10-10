"""
Product Targeting and Exclusion Rules Engine for Megathon X (PS1: Green Customer Insights).

Implements deterministic business eligibility checks, frozen cutoff observation windows,
and standardized exclusion reason codes for products GP01–GP04 matching the JSON contract.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import json


# ---------------------------------------------------------------------------
# 1. Temporal Windows & Cutoff Constants
# ---------------------------------------------------------------------------

OBSERVATION_WINDOW_START: str = "2026-01-01"
OBSERVATION_WINDOW_END: str = "2026-06-30"
CUTOFF_DATE: str = "2026-06-30"
OUTCOME_WINDOW_START: str = "2026-07-01"
OUTCOME_WINDOW_END: str = "2026-12-31"


# ---------------------------------------------------------------------------
# 2. Product Catalogue Enums & Mappings (GP01 - GP04)
# ---------------------------------------------------------------------------

class ProductCode(str, Enum):
    GP01 = "GP01"  # Green Home Retrofit
    GP02 = "GP02"  # Solar PV & Storage
    GP03 = "GP03"  # Clean Transport & EV Finance
    GP04 = "GP04"  # Paperless Banking & Digital Journey


class OpportunityKey(str, Enum):
    GREEN_HOME = "GREEN_HOME"
    SOLAR_FINANCE = "SOLAR_FINANCE"
    EV_FINANCE = "EV_FINANCE"
    PAPERLESS_BANKING = "PAPERLESS_BANKING"


PRODUCT_TO_OPPORTUNITY: Dict[ProductCode, OpportunityKey] = {
    ProductCode.GP01: OpportunityKey.GREEN_HOME,
    ProductCode.GP02: OpportunityKey.SOLAR_FINANCE,
    ProductCode.GP03: OpportunityKey.EV_FINANCE,
    ProductCode.GP04: OpportunityKey.PAPERLESS_BANKING,
}

OPPORTUNITY_TO_PRODUCT: Dict[OpportunityKey, ProductCode] = {
    v: k for k, v in PRODUCT_TO_OPPORTUNITY.items()
}

# Cross-reference alias mapping for legacy slide numbering (where Slide 4 numbered EV as 1)
PRODUCT_ALIASES: Dict[str, ProductCode] = {
    "GP01": ProductCode.GP01,
    "GP02": ProductCode.GP02,
    "GP03": ProductCode.GP03,
    "GP04": ProductCode.GP04,
    "GREEN_HOME": ProductCode.GP01,
    "SOLAR_FINANCE": ProductCode.GP02,
    "EV_FINANCE": ProductCode.GP03,
    "PAPERLESS_BANKING": ProductCode.GP04,
    "EV": ProductCode.GP03,
    "SOLAR": ProductCode.GP02,
    "PAPERLESS": ProductCode.GP04,
}

PRODUCT_CATALOGUE_SPECS: Dict[ProductCode, Dict[str, Any]] = {
    ProductCode.GP01: {
        "name": "Green Home Retrofit Loan",
        "opportunity": OpportunityKey.GREEN_HOME,
        "target_persona": "Homeowners in low-efficiency dwellings (EPC D-G) with elevated heating bills",
        "primary_signals": ["high_gas_spend", "low_epc_rating", "homeowner_tenure"],
        "carbon_lever": "Natural gas combustion displacement (0.18231 kg CO2e/kWh) via thermal insulation & heat pump",
        "hard_eligibility": ["Must be verified property owner", "Property EPC D, E, F, or G", "No credit distress"],
    },
    ProductCode.GP02: {
        "name": "Solar PV & Battery Storage Finance",
        "opportunity": OpportunityKey.SOLAR_FINANCE,
        "target_persona": "Homeowners with high daytime electricity consumption and independent roof rights",
        "primary_signals": ["high_electricity_spend", "detached_or_semi_property", "solar_uninstalled"],
        "carbon_lever": "UK grid electricity displacement (0.14395 kg CO2e/kWh generation + T&D)",
        "hard_eligibility": ["Must be verified property owner", "Non-flat residential dwelling", "No existing solar PV"],
    },
    ProductCode.GP03: {
        "name": "Clean Transport & EV Finance",
        "opportunity": OpportunityKey.EV_FINANCE,
        "target_persona": "Regular fossil fuel commuters with high recurring fuel spend and ICE vehicle ownership",
        "primary_signals": ["recurring_fuel_spend", "high_annual_mileage", "existing_ice_vehicle"],
        "carbon_lever": "Petrol (0.17048 kg CO2e/km) or Diesel (0.17265 kg CO2e/km) displaced by BEV (0.06012 kg CO2e/km)",
        "hard_eligibility": ["Must currently drive/own an ICE vehicle", "Must NOT already own a Battery EV", "No credit distress"],
    },
    ProductCode.GP04: {
        "name": "Paperless Banking & Digital Journey",
        "opportunity": OpportunityKey.PAPERLESS_BANKING,
        "target_persona": "Active online/mobile banking users who still receive paper postal statements",
        "primary_signals": ["physical_paper_statements", "active_app_logins", "verified_digital_contact"],
        "carbon_lever": "Paper production (1198.24 kg CO2e/tonne) and postal mail logistics avoidance",
        "hard_eligibility": ["Must currently receive paper statements", "Must have active digital banking profile"],
    },
}


# ---------------------------------------------------------------------------
# 3. Standardized Reason Code Master List (Exact 12 Immutable Reason Codes)
# ---------------------------------------------------------------------------

class ExclusionReasonCode(str, Enum):
    EXC_NOT_HOMEOWNER = "EXC_NOT_HOMEOWNER"
    EXC_ALREADY_EV_OWNER = "EXC_ALREADY_EV_OWNER"
    EXC_ALREADY_PAPERLESS = "EXC_ALREADY_PAPERLESS"
    EXC_ALREADY_SOLAR_INSTALLED = "EXC_ALREADY_SOLAR_INSTALLED"
    EXC_PROPERTY_MAX_EFFICIENCY = "EXC_PROPERTY_MAX_EFFICIENCY"
    EXC_PROPERTY_TYPE_INELIGIBLE = "EXC_PROPERTY_TYPE_INELIGIBLE"
    EXC_NO_VEHICLE_USAGE = "EXC_NO_VEHICLE_USAGE"
    EXC_NO_DIGITAL_CHANNEL = "EXC_NO_DIGITAL_CHANNEL"
    EXC_FINANCIAL_DISTRESS = "EXC_FINANCIAL_DISTRESS"
    EXC_MARKETING_OPT_OUT = "EXC_MARKETING_OPT_OUT"
    EXC_RECENT_APPLICATION_DECLINE = "EXC_RECENT_APPLICATION_DECLINE"
    EXC_AGE_OR_RESIDENCY_INELIGIBLE = "EXC_AGE_OR_RESIDENCY_INELIGIBLE"


EXCLUSION_REASON_DESCRIPTIONS: Dict[ExclusionReasonCode, Dict[str, Any]] = {
    ExclusionReasonCode.EXC_NOT_HOMEOWNER: {
        "description": "Customer is a tenant, lodger, or non-homeowner; cannot alter property fabric.",
        "products": [ProductCode.GP01, ProductCode.GP02],
    },
    ExclusionReasonCode.EXC_ALREADY_EV_OWNER: {
        "description": "Customer already owns or leases a battery electric vehicle.",
        "products": [ProductCode.GP03],
    },
    ExclusionReasonCode.EXC_ALREADY_PAPERLESS: {
        "description": "Customer is already enrolled in 100% digital paperless statements.",
        "products": [ProductCode.GP04],
    },
    ExclusionReasonCode.EXC_ALREADY_SOLAR_INSTALLED: {
        "description": "Customer property already has an active solar PV installation.",
        "products": [ProductCode.GP02],
    },
    ExclusionReasonCode.EXC_PROPERTY_MAX_EFFICIENCY: {
        "description": "Customer property already has EPC rating A or B (maximum standard).",
        "products": [ProductCode.GP01],
    },
    ExclusionReasonCode.EXC_PROPERTY_TYPE_INELIGIBLE: {
        "description": "Property is a flat, apartment, or communal building without sovereign roof rights.",
        "products": [ProductCode.GP02],
    },
    ExclusionReasonCode.EXC_NO_VEHICLE_USAGE: {
        "description": "Customer has zero fuel spend and no recorded vehicle ownership.",
        "products": [ProductCode.GP03],
    },
    ExclusionReasonCode.EXC_NO_DIGITAL_CHANNEL: {
        "description": "Customer has no active online/mobile banking profile or verified digital contact.",
        "products": [ProductCode.GP04],
    },
    ExclusionReasonCode.EXC_FINANCIAL_DISTRESS: {
        "description": "Customer in active delinquency, arrears, or forbearance (FCA Consumer Duty).",
        "products": [ProductCode.GP01, ProductCode.GP02, ProductCode.GP03],
    },
    ExclusionReasonCode.EXC_MARKETING_OPT_OUT: {
        "description": "Customer has opted out of direct marketing communications (GDPR Art. 21 / PECR).",
        "products": [ProductCode.GP01, ProductCode.GP02, ProductCode.GP03, ProductCode.GP04],
    },
    ExclusionReasonCode.EXC_RECENT_APPLICATION_DECLINE: {
        "description": "Customer had a credit application declined within the 90-day cooling-off window.",
        "products": [ProductCode.GP01, ProductCode.GP02, ProductCode.GP03],
    },
    ExclusionReasonCode.EXC_AGE_OR_RESIDENCY_INELIGIBLE: {
        "description": "Customer is under 18 years old or not a verified UK permanent resident.",
        "products": [ProductCode.GP01, ProductCode.GP02, ProductCode.GP03, ProductCode.GP04],
    },
}


# ---------------------------------------------------------------------------
# 4. Frozen Contract Data Structures
# ---------------------------------------------------------------------------

@dataclass
class SustainabilityImpact:
    estimated_annual_reduction_kg: float
    unit: str = "kg CO2e"
    method: str = "GHG Protocol project emissions accounting"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TargetingDecision:
    customer_id: str
    product_code: str
    opportunity: str
    cutoff_date: str
    is_eligible: bool
    targeting_status: str  # "QUALIFIED" or "EXCLUDED"
    exclusion_reason_codes: List[str]
    propensity: Optional[float] = None
    confidence: Optional[float] = None
    reason_codes: List[str] = field(default_factory=list)
    sustainability_impact: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# 5. Deterministic Exclusion Rules Engine
# ---------------------------------------------------------------------------

class ExclusionEngine:
    """
    Deterministic rules engine executing authorized institution exclusion logic.
    Propensity never determines eligibility.
    """

    @staticmethod
    def resolve_product(product_ref: Any) -> ProductCode:
        """Resolves string, enum, or opportunity name to canonical ProductCode."""
        if isinstance(product_ref, ProductCode):
            return product_ref
        key = str(product_ref).upper().strip()
        if key in PRODUCT_ALIASES:
            return PRODUCT_ALIASES[key]
        raise ValueError(f"Unknown product reference: {product_ref}")

    @classmethod
    def evaluate(
        cls,
        customer_profile: Dict[str, Any],
        product_ref: Any,
        cutoff_date: str = CUTOFF_DATE,
    ) -> TargetingDecision:
        """
        Evaluates a customer against the business exclusions for a specific product.
        Returns a frozen TargetingDecision contract object.
        """
        product = cls.resolve_product(product_ref)
        opp_key = PRODUCT_TO_OPPORTUNITY[product]
        customer_id = str(customer_profile.get("customer_id", "UNKNOWN"))

        exclusions: List[str] = []

        # -------------------------------------------------------------------
        # Rule 10: Marketing Opt-out (Universal)
        # -------------------------------------------------------------------
        if customer_profile.get("marketing_consent") is False:
            exclusions.append(ExclusionReasonCode.EXC_MARKETING_OPT_OUT.value)

        # -------------------------------------------------------------------
        # Rule 12: Age & Residency Ineligibility (Universal)
        # -------------------------------------------------------------------
        age = customer_profile.get("age")
        uk_resident = customer_profile.get("uk_resident", True)
        if (age is not None and age < 18) or (uk_resident is False):
            exclusions.append(ExclusionReasonCode.EXC_AGE_OR_RESIDENCY_INELIGIBLE.value)

        # -------------------------------------------------------------------
        # Credit Products Common Rules (GP01, GP02, GP03)
        # -------------------------------------------------------------------
        if product in (ProductCode.GP01, ProductCode.GP02, ProductCode.GP03):
            # Rule 9: Financial Distress
            if (
                customer_profile.get("is_in_arrears") is True
                or customer_profile.get("delinquency_status") in ("ARREARS", "DEFAULT", "VULNERABLE")
                or customer_profile.get("credit_score_band") == "SEVERE_DISTRESS"
            ):
                exclusions.append(ExclusionReasonCode.EXC_FINANCIAL_DISTRESS.value)

            # Rule 11: Recent Application Decline (90-day cooling off)
            days_since_decline = customer_profile.get("days_since_last_credit_decline")
            if days_since_decline is not None and days_since_decline < 90:
                exclusions.append(ExclusionReasonCode.EXC_RECENT_APPLICATION_DECLINE.value)

        # -------------------------------------------------------------------
        # Product-Specific Rules: GP01 (Green Home)
        # -------------------------------------------------------------------
        if product == ProductCode.GP01:
            # Rule 1: Non-homeowner
            homeowner_status = str(customer_profile.get("homeowner_status", "")).upper()
            if homeowner_status not in ("OWNER", "OWNER_OCCUPIER", "MORTGAGED"):
                exclusions.append(ExclusionReasonCode.EXC_NOT_HOMEOWNER.value)

            # Rule 5: Property EPC Already Max Efficiency
            epc = str(customer_profile.get("property_epc_rating", "")).upper()
            if epc in ("A", "B"):
                exclusions.append(ExclusionReasonCode.EXC_PROPERTY_MAX_EFFICIENCY.value)

        # -------------------------------------------------------------------
        # Product-Specific Rules: GP02 (Solar PV)
        # -------------------------------------------------------------------
        elif product == ProductCode.GP02:
            # Rule 1: Non-homeowner
            homeowner_status = str(customer_profile.get("homeowner_status", "")).upper()
            if homeowner_status not in ("OWNER", "OWNER_OCCUPIER", "MORTGAGED"):
                exclusions.append(ExclusionReasonCode.EXC_NOT_HOMEOWNER.value)

            # Rule 4: Already Solar Installed
            if customer_profile.get("has_solar") is True:
                exclusions.append(ExclusionReasonCode.EXC_ALREADY_SOLAR_INSTALLED.value)

            # Rule 6: Ineligible Property Type (Flats / Apartments without private roof)
            prop_type = str(customer_profile.get("property_type", "")).upper()
            if prop_type in ("FLAT", "APARTMENT", "MAISONETTE_SHARED", "COMMUNAL"):
                exclusions.append(ExclusionReasonCode.EXC_PROPERTY_TYPE_INELIGIBLE.value)

        # -------------------------------------------------------------------
        # Product-Specific Rules: GP03 (EV Finance)
        # -------------------------------------------------------------------
        elif product == ProductCode.GP03:
            # Rule 2: Already EV Owner
            if customer_profile.get("is_ev_owner") is True:
                exclusions.append(ExclusionReasonCode.EXC_ALREADY_EV_OWNER.value)

            # Rule 7: No Vehicle Usage / Non-driver
            has_vehicle = customer_profile.get("has_vehicle", True)
            fuel_spend = customer_profile.get("fuel_spend_6m", 0)
            mileage = customer_profile.get("annual_mileage", 0)
            if not has_vehicle or (fuel_spend <= 0 and mileage <= 0):
                exclusions.append(ExclusionReasonCode.EXC_NO_VEHICLE_USAGE.value)

        # -------------------------------------------------------------------
        # Product-Specific Rules: GP04 (Paperless Banking)
        # -------------------------------------------------------------------
        elif product == ProductCode.GP04:
            # Rule 3: Already Paperless
            if customer_profile.get("is_paperless") is True:
                exclusions.append(ExclusionReasonCode.EXC_ALREADY_PAPERLESS.value)

            # Rule 8: No Digital Channel / App Access
            has_digital = customer_profile.get("has_digital_banking", True)
            logins = customer_profile.get("digital_logins_90d", 1)
            if not has_digital or logins <= 0:
                exclusions.append(ExclusionReasonCode.EXC_NO_DIGITAL_CHANNEL.value)

        # -------------------------------------------------------------------
        # Construct Standard Contract Decision
        # -------------------------------------------------------------------
        is_eligible = len(exclusions) == 0
        targeting_status = "QUALIFIED" if is_eligible else "EXCLUDED"

        return TargetingDecision(
            customer_id=customer_id,
            product_code=product.value,
            opportunity=opp_key.value,
            cutoff_date=cutoff_date,
            is_eligible=is_eligible,
            targeting_status=targeting_status,
            exclusion_reason_codes=sorted(list(set(exclusions))),
            propensity=None,
            confidence=None,
            reason_codes=[],
            sustainability_impact=None,
        )


def evaluate_customer_targeting(
    customer_profile: Dict[str, Any],
    product_code: str,
    cutoff_date: str = CUTOFF_DATE,
) -> Dict[str, Any]:
    """
    Public entrypoint for downstream service pipelines.
    Returns dictionary conforming directly to frozen TargetingDecision JSON schema.
    """
    decision = ExclusionEngine.evaluate(customer_profile, product_code, cutoff_date)
    return decision.to_dict()
