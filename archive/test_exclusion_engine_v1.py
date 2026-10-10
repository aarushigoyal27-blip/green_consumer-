"""
Unit tests for Product Targeting and Exclusion Rules Engine.
Validates window definitions, product mappings, exactly 12 reason codes,
and JSON contract compatibility.
"""

import unittest
from datetime import datetime
from exclusion_engine import (
    ExclusionEngine,
    ProductCode,
    OpportunityKey,
    ExclusionReasonCode,
    OBSERVATION_WINDOW_START,
    OBSERVATION_WINDOW_END,
    CUTOFF_DATE,
    OUTCOME_WINDOW_START,
    OUTCOME_WINDOW_END,
    PRODUCT_CATALOGUE_SPECS,
    EXCLUSION_REASON_DESCRIPTIONS,
    evaluate_customer_targeting,
)


class TestExclusionEngine(unittest.TestCase):

    def test_window_dates_strictly_defined_and_disjoint(self):
        """Verification Criterion 1: Feature and outcome window dates clearly defined without overlap."""
        obs_start = datetime.strptime(OBSERVATION_WINDOW_START, "%Y-%m-%d")
        obs_end = datetime.strptime(OBSERVATION_WINDOW_END, "%Y-%m-%d")
        cutoff = datetime.strptime(CUTOFF_DATE, "%Y-%m-%d")
        out_start = datetime.strptime(OUTCOME_WINDOW_START, "%Y-%m-%d")
        out_end = datetime.strptime(OUTCOME_WINDOW_END, "%Y-%m-%d")

        # 1. Observation window is chronological
        self.assertLess(obs_start, obs_end)
        self.assertEqual(obs_end, cutoff)

        # 2. Cutoff matches June 30, 2026
        self.assertEqual(CUTOFF_DATE, "2026-06-30")

        # 3. Outcome window starts strictly after cutoff (July 1, 2026)
        self.assertGreater(out_start, cutoff)
        self.assertEqual(OUTCOME_WINDOW_START, "2026-07-01")
        self.assertEqual(OUTCOME_WINDOW_END, "2026-12-31")

        # 4. Strict disjointness (Zero overlap)
        self.assertLess(obs_end, out_start)
        self.assertEqual((out_start - obs_end).days, 1)

    def test_all_four_products_catalogued(self):
        """Verification Criterion 2: All four products (GP01–GP04) assigned clear eligibility criteria and personas."""
        codes = [ProductCode.GP01, ProductCode.GP02, ProductCode.GP03, ProductCode.GP04]
        self.assertEqual(len(codes), 4)

        for code in codes:
            self.assertIn(code, PRODUCT_CATALOGUE_SPECS)
            spec = PRODUCT_CATALOGUE_SPECS[code]
            self.assertTrue(len(spec["name"]) > 0)
            self.assertTrue(len(spec["target_persona"]) > 0)
            self.assertTrue(len(spec["primary_signals"]) > 0)
            self.assertTrue(len(spec["carbon_lever"]) > 0)
            self.assertTrue(len(spec["hard_eligibility"]) > 0)

        # Confirm specific mappings
        self.assertEqual(PRODUCT_CATALOGUE_SPECS[ProductCode.GP01]["opportunity"], OpportunityKey.GREEN_HOME)
        self.assertEqual(PRODUCT_CATALOGUE_SPECS[ProductCode.GP02]["opportunity"], OpportunityKey.SOLAR_FINANCE)
        self.assertEqual(PRODUCT_CATALOGUE_SPECS[ProductCode.GP03]["opportunity"], OpportunityKey.EV_FINANCE)
        self.assertEqual(PRODUCT_CATALOGUE_SPECS[ProductCode.GP04]["opportunity"], OpportunityKey.PAPERLESS_BANKING)

    def test_exactly_twelve_standardized_reason_codes(self):
        """Verification Criterion 3: Exactly ~12 standardized exclusion reason codes cataloged and mapped."""
        all_codes = list(ExclusionReasonCode)
        self.assertEqual(len(all_codes), 12, f"Expected exactly 12 standardized reason codes, got {len(all_codes)}")

        # Verify all start with EXC_
        for code in all_codes:
            self.assertTrue(code.value.startswith("EXC_"), f"Code {code} must start with 'EXC_'")
            self.assertIn(code, EXCLUSION_REASON_DESCRIPTIONS)

        # Expected core codes
        expected_subset = {
            "EXC_NOT_HOMEOWNER",
            "EXC_ALREADY_EV_OWNER",
            "EXC_ALREADY_PAPERLESS",
            "EXC_ALREADY_SOLAR_INSTALLED",
            "EXC_PROPERTY_MAX_EFFICIENCY",
            "EXC_PROPERTY_TYPE_INELIGIBLE",
            "EXC_NO_VEHICLE_USAGE",
            "EXC_NO_DIGITAL_CHANNEL",
            "EXC_FINANCIAL_DISTRESS",
            "EXC_MARKETING_OPT_OUT",
            "EXC_RECENT_APPLICATION_DECLINE",
            "EXC_AGE_OR_RESIDENCY_INELIGIBLE",
        }
        actual_codes = {c.value for c in all_codes}
        self.assertEqual(actual_codes, expected_subset)

    def test_ev_owner_exclusion_from_ev_finance(self):
        """Business Logic: EV owner -> Exclude from EV finance."""
        profile = {
            "customer_id": "C1001",
            "is_ev_owner": True,
            "has_vehicle": True,
            "fuel_spend_6m": 400,
        }
        decision = evaluate_customer_targeting(profile, "GP03")
        self.assertFalse(decision["is_eligible"])
        self.assertEqual(decision["targeting_status"], "EXCLUDED")
        self.assertIn("EXC_ALREADY_EV_OWNER", decision["exclusion_reason_codes"])

    def test_non_homeowner_exclusion_from_solar_and_green_home(self):
        """Business Logic: Non-homeowner -> Exclude from Solar and Green Home offers."""
        tenant_profile = {
            "customer_id": "C1002",
            "homeowner_status": "TENANT",
            "gas_spend_6m": 800,
            "electricity_spend_6m": 600,
        }

        # Check Green Home (GP01)
        res_home = evaluate_customer_targeting(tenant_profile, "GP01")
        self.assertFalse(res_home["is_eligible"])
        self.assertIn("EXC_NOT_HOMEOWNER", res_home["exclusion_reason_codes"])

        # Check Solar (GP02)
        res_solar = evaluate_customer_targeting(tenant_profile, "GP02")
        self.assertFalse(res_solar["is_eligible"])
        self.assertIn("EXC_NOT_HOMEOWNER", res_solar["exclusion_reason_codes"])

        # But tenant can qualify for EV or Paperless if criteria met!
        res_paperless = evaluate_customer_targeting(
            {"customer_id": "C1002", "is_paperless": False, "digital_logins_90d": 5},
            "GP04"
        )
        self.assertTrue(res_paperless["is_eligible"])
        self.assertEqual(res_paperless["exclusion_reason_codes"], [])

    def test_already_paperless_exclusion_from_paperless(self):
        """Business Logic: Already paperless -> Exclude from Paperless offer."""
        profile = {
            "customer_id": "C1003",
            "is_paperless": True,
            "has_digital_banking": True,
        }
        res = evaluate_customer_targeting(profile, "GP04")
        self.assertFalse(res["is_eligible"])
        self.assertEqual(res["targeting_status"], "EXCLUDED")
        self.assertIn("EXC_ALREADY_PAPERLESS", res["exclusion_reason_codes"])

    def test_solar_specific_exclusions(self):
        """Solar PV exclusions: already installed or flat property."""
        # 1. Already installed
        profile_has_solar = {
            "customer_id": "C1004",
            "homeowner_status": "OWNER",
            "has_solar": True,
            "property_type": "DETACHED",
        }
        res1 = evaluate_customer_targeting(profile_has_solar, "GP02")
        self.assertFalse(res1["is_eligible"])
        self.assertIn("EXC_ALREADY_SOLAR_INSTALLED", res1["exclusion_reason_codes"])

        # 2. Ineligible flat property type
        profile_flat = {
            "customer_id": "C1005",
            "homeowner_status": "OWNER",
            "has_solar": False,
            "property_type": "FLAT",
        }
        res2 = evaluate_customer_targeting(profile_flat, "GP02")
        self.assertFalse(res2["is_eligible"])
        self.assertIn("EXC_PROPERTY_TYPE_INELIGIBLE", res2["exclusion_reason_codes"])

    def test_green_home_high_epc_exclusion(self):
        """Green Home exclusion: Property already top EPC (A or B)."""
        profile_a = {
            "customer_id": "C1006",
            "homeowner_status": "OWNER",
            "property_epc_rating": "A",
        }
        res = evaluate_customer_targeting(profile_a, "GP01")
        self.assertFalse(res["is_eligible"])
        self.assertIn("EXC_PROPERTY_MAX_EFFICIENCY", res["exclusion_reason_codes"])

    def test_regulatory_and_protection_exclusions(self):
        """Universal exclusions: marketing opt-out, arrears, cooling-off."""
        # Marketing opt out
        res_mkt = evaluate_customer_targeting(
            {"customer_id": "C1007", "marketing_consent": False},
            "GP01"
        )
        self.assertIn("EXC_MARKETING_OPT_OUT", res_mkt["exclusion_reason_codes"])

        # Financial distress
        res_arr = evaluate_customer_targeting(
            {"customer_id": "C1008", "homeowner_status": "OWNER", "is_in_arrears": True},
            "GP01"
        )
        self.assertIn("EXC_FINANCIAL_DISTRESS", res_arr["exclusion_reason_codes"])

        # Recent credit decline (<90 days)
        res_decl = evaluate_customer_targeting(
            {"customer_id": "C1009", "homeowner_status": "OWNER", "days_since_last_credit_decline": 30},
            "GP01"
        )
        self.assertIn("EXC_RECENT_APPLICATION_DECLINE", res_decl["exclusion_reason_codes"])

    def test_frozen_json_contract_structure(self):
        """Verification Criterion 4: Design decisions fully validated against frozen JSON contract."""
        qualified_profile = {
            "customer_id": "C10010",
            "homeowner_status": "OWNER",
            "property_epc_rating": "E",
            "is_in_arrears": False,
            "marketing_consent": True,
            "age": 42,
            "uk_resident": True,
        }
        decision = evaluate_customer_targeting(qualified_profile, "GP01")

        # Required fields in contract
        required_fields = [
            "customer_id",
            "product_code",
            "opportunity",
            "cutoff_date",
            "is_eligible",
            "targeting_status",
            "exclusion_reason_codes",
            "propensity",
            "confidence",
            "reason_codes",
            "sustainability_impact",
        ]
        for field_name in required_fields:
            self.assertIn(field_name, decision)

        self.assertEqual(decision["customer_id"], "C10010")
        self.assertEqual(decision["product_code"], "GP01")
        self.assertEqual(decision["opportunity"], "GREEN_HOME")
        self.assertEqual(decision["cutoff_date"], "2026-06-30")
        self.assertTrue(decision["is_eligible"])
        self.assertEqual(decision["targeting_status"], "QUALIFIED")
        self.assertEqual(decision["exclusion_reason_codes"], [])


if __name__ == "__main__":
    unittest.main()
