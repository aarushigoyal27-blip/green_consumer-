"""Customer-360 / contract field names -> carbon-engine input names.

Source of truth for the right-hand side: config/contract.json
(schemas.customer_profile_input.properties, contract v2.1.0). A test checks that
every source field below exists in the contract, so a rename breaks the build
instead of silently feeding None to the carbon engine.
"""
CARBON_FIELD_MAP = {
    # carbon input             : contract field (units per contract v2.1.0)
    "vehicle_fuel_type":         "vehicle_fuel_type",          # petrol|diesel|hybrid|ev (+ aliases)
    "annual_mileage_km":         "annual_mileage_km",          # km/yr, NOT miles
    "annual_fuel_spend_gbp":     "annual_fuel_spend",          # GBP/yr, annualised
    "annual_electricity_kwh":    "baseline_electricity_kwh",   # kWh/yr, annualised
    "annual_gas_kwh":            "baseline_gas_kwh",           # kWh/yr gross CV, annualised
    "paper_statements_per_year": "paper_statements_per_year",  # count/yr
}
# Not in the contract, so not mapped: solar_system_kwp. GP03 therefore always uses the
# documented default system size from config/carbon_assumptions.yaml.


def to_carbon_inputs(customer: dict) -> dict:
    return {carbon_key: customer.get(src_key) for carbon_key, src_key in CARBON_FIELD_MAP.items()}
