"""
Unit tests for strict LLM grounding and regex-based validator.
"""

import unittest
from grounding import (
    explain,
    validate,
    simulate_hallucination,
    extract_numbers,
    UnsupportedNumber,
    GROUNDING_SYSTEM_PROMPT,
)


class TestGroundingPipeline(unittest.TestCase):

    def setUp(self):
        self.sample_payload = {
            "customer_id": "C10001",
            "opportunity": "EV_FINANCE",
            "propensity": 0.84,
            "confidence": 0.87,
            "reason_codes": ["HIGH_FUEL_SPEND", "HIGH_ANNUAL_MILEAGE", "EXISTING_VEHICLE"],
            "annual_fuel_spend": 2400,
            "annual_mileage": 12000,
            "estimated_annual_reduction_kg": 1200,
            "unit": "kg CO2e",
            "method": "GHG Protocol project emissions accounting",
            "data_cutoff_date": "2026-10-10",
            "subsidies_available": None,
        }

    def test_explain_generates_grounded_response(self):
        """Verification Criterion 1: Pass test payload to explain() and generate response."""
        text = explain(self.sample_payload)
        self.assertIsInstance(text, str)
        self.assertTrue(len(text) > 0)

        # Check prompt rules enforcement
        self.assertIn("not available", text.lower())  # null subsidies_available
        self.assertIn("estimate", text.lower())        # estimate labeled

        # Validate that explain's output has zero hallucinations
        unsupported = validate(text, self.sample_payload)
        self.assertEqual(unsupported, [], f"Expected 0 unsupported numbers, got: {unsupported}")

    def test_deliberate_hallucination_detected(self):
        """Verification Criteria 2 & 3: Inject unsupported numbers and verify validate() flags them."""
        base_text = explain(self.sample_payload)
        hallucinated_text = simulate_hallucination(
            base_text,
            injected_claims=[
                "You qualify for a bonus incentive of £450.",
                "We project an additional 999 kg CO2e savings.",
                "Your interest rate will be fixed at 5.5%.",
            ]
        )

        unsupported = validate(hallucinated_text, self.sample_payload)
        self.assertTrue(len(unsupported) >= 3, f"Expected at least 3 unsupported numbers, got: {unsupported}")

        # Verify that specific injected numbers are flagged
        self.assertIn("450", unsupported)
        self.assertIn(450, unsupported)
        self.assertIn("£450", unsupported)

        self.assertIn("999", unsupported)
        self.assertIn(999, unsupported)

        self.assertIn("5.5", unsupported)
        self.assertIn(5.5, unsupported)
        self.assertIn("5.5%", unsupported)

    def test_unit_conversions_tonnes_to_kg(self):
        """Verify matching '1.2 t' and '1.2 tonnes' to 1200 kg in payload."""
        payload = {"estimated_annual_reduction_kg": 1200}

        # 1.2 t -> 1200 kg
        text1 = "Estimated annual reduction is 1.2 t CO2e."
        self.assertEqual(validate(text1, payload), [])

        # 1.2 tonnes -> 1200 kg
        text2 = "Estimated annual reduction is 1.2 tonnes of CO2e."
        self.assertEqual(validate(text2, payload), [])

        # Formatted 1,200 kg -> 1200 kg
        text3 = "Estimated annual reduction is 1,200 kg CO2e."
        self.assertEqual(validate(text3, payload), [])

        # Hallucinated unit value: 1.5 t (1500 kg != 1200 kg)
        text_hallucinated = "Estimated annual reduction is 1.5 t CO2e."
        unsupported = validate(text_hallucinated, payload)
        self.assertEqual(len(unsupported), 1)
        self.assertIn("1.5", unsupported)
        self.assertIn(1.5, unsupported)

    def test_unit_conversions_mwh_to_kwh(self):
        """Verify matching '4.8 MWh' to 4800 kWh."""
        payload = {"baseline_electricity_kwh": 4800}

        # 4.8 MWh -> 4800 kWh
        text_valid = "Baseline electricity consumption is 4.8 MWh."
        self.assertEqual(validate(text_valid, payload), [])

        # Hallucinated: 5.2 MWh
        text_invalid = "Baseline electricity consumption is 5.2 MWh."
        unsupported = validate(text_invalid, payload)
        self.assertEqual(len(unsupported), 1)
        self.assertIn("5.2", unsupported)

    def test_multiplier_conversions_k(self):
        """Verify matching '£350k' to 350000."""
        payload = {"property_value": 350000}

        text_valid1 = "Current property valuation is £350k."
        self.assertEqual(validate(text_valid1, payload), [])

        text_valid2 = "Current property valuation is £350,000."
        self.assertEqual(validate(text_valid2, payload), [])

        # Hallucinated valuation: £400k
        text_invalid = "Current property valuation is £400k."
        unsupported = validate(text_invalid, payload)
        self.assertEqual(len(unsupported), 1)
        self.assertIn(400000, unsupported)

    def test_percentage_and_decimal_conversions(self):
        """Verify matching 84% to 0.84."""
        payload = {"propensity": 0.84, "confidence": 0.87}

        text_valid = "Propensity is 84% with a model confidence of 0.87."
        self.assertEqual(validate(text_valid, payload), [])

        # Hallucinated percentage: 92%
        text_invalid = "Propensity is 92% with a model confidence of 0.87."
        unsupported = validate(text_invalid, payload)
        self.assertEqual(len(unsupported), 1)
        self.assertIn("92", unsupported)
        self.assertIn("92%", unsupported)

    def test_derived_or_computed_number_is_flagged(self):
        """Rule 4: Never compute or derive new numbers (e.g. summing values)."""
        payload = {
            "baseline_gas_kwh": 12000,
            "baseline_electricity_kwh": 4800,
        }
        # 12000 + 4800 = 16800. The LLM calculated 16,800, which is NOT in payload.
        text_computed = (
            "Baseline gas is 12,000 kWh and electricity is 4,800 kWh. "
            "Total purchased energy is 16,800 kWh."
        )
        unsupported = validate(text_computed, payload)
        self.assertEqual(len(unsupported), 1)
        self.assertIn("16,800", unsupported)
        self.assertIn(16800, unsupported)

    def test_chemical_formulas_do_not_trigger_false_positives(self):
        """Ensure chemical notation (CO2, CO2e, CO₂e) does not register '2' as a number."""
        payload = {"customer_id": "C10001"}
        text = "Reduces CO2 and CO2e emissions as well as CO₂e significantly."
        unsupported = validate(text, payload)
        self.assertEqual(unsupported, [])

    def test_null_field_substitution_flagged(self):
        """Rule 3: Output 'not available' when field is null; inventing a value is flagged."""
        payload = {
            "customer_id": "C10001",
            "government_grant_gbp": None,
        }
        # If the LLM invents a grant of £500
        text_invented = "Government grant of £500 is available for customer C10001."
        unsupported = validate(text_invented, payload)
        self.assertEqual(len(unsupported), 1)
        self.assertIn("500", unsupported)
        self.assertIn("£500", unsupported)

    def test_custom_llm_fn_hook(self):
        """Verify custom LLM function receives the exact prompt rules."""
        received = {}

        def mock_llm(sys_prompt, user_prompt):
            received["sys"] = sys_prompt
            received["user"] = user_prompt
            return "Customer C10001 has 84% propensity."

        out = explain(self.sample_payload, llm_fn=mock_llm)
        self.assertEqual(out, "Customer C10001 has 84% propensity.")
        self.assertIn("Use ONLY numbers explicitly present in the payload", received["sys"])
        self.assertIn("Explicitly label any estimates as estimates", received["sys"])
        self.assertIn("Output \"not available\" when a payload field is null", received["sys"])
        self.assertIn("Never compute, calculate, or derive any new numbers", received["sys"])


if __name__ == "__main__":
    unittest.main()
