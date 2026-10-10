"""Single place where opportunity names meet GP product codes.

Everything inside the recommendation engine is keyed by opportunity name.
GP codes appear only in output records, via OPPORTUNITY_TO_CODE. If the team
renumbers products, this dict is the only thing that changes.
"""
OPPORTUNITIES = ("EV_FINANCE", "GREEN_HOME", "SOLAR_FINANCE", "PAPERLESS_BANKING")

# Numbering from Lloyds PS1 spec, Section 2 table (and config/green_products.csv).
OPPORTUNITY_TO_CODE = {
    "EV_FINANCE": "GP01",
    "GREEN_HOME": "GP02",
    "SOLAR_FINANCE": "GP03",
    "PAPERLESS_BANKING": "GP04",
}

# Opportunities whose headline impact is kg CO2e. Paperless reports kg paper, never CO2e.
CARBON_OPPORTUNITIES = ("EV_FINANCE", "GREEN_HOME", "SOLAR_FINANCE")


def code_for(opportunity: str) -> str:
    return OPPORTUNITY_TO_CODE[opportunity]
