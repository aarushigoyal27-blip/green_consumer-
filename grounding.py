"""
Grounding and Validation Module for Megathon LLM Pipeline.

Provides:
- explain(payload: dict) -> str:
    Calls the LLM enforcing strict system prompt rules to prevent hallucinations:
    1. Use ONLY numbers explicitly present in the payload.
    2. Explicitly label any estimates as estimates.
    3. Output "not available" when a payload field is null.
    4. Never compute, calculate, or derive any new numbers.
- validate(text: str, payload: dict) -> list:
    Extracts every number in the LLM output via regex, cross-references with payload
    accounting for formatting (commas, currency, decimals) and unit conversions
    (e.g., matching '1.2 t' to 1200 kg, '4.8 MWh' to 4800 kWh, '84%' to 0.84),
    and returns a list of any unsupported or invented numbers.
"""

import json
import math
import os
import re
import urllib.request
import urllib.error
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


# ---------------------------------------------------------------------------
# Grounding System Prompt
# ---------------------------------------------------------------------------

GROUNDING_SYSTEM_PROMPT = """You are a strictly grounded AI explanation assistant for customer insights.
Your sole job is to translate the provided structured payload into a clear, customer-friendly plain-language explanation.

You MUST obey the following grounding rules without exception:
1. Use ONLY numbers explicitly present in the payload. Never introduce, invent, assume, or hallucinate any numbers.
2. Explicitly label any estimates as estimates (e.g., "estimated annual reduction of...", "indicative estimate").
3. Output "not available" when a payload field is null or missing. Never guess, fill in, or substitute values.
4. Never compute, calculate, or derive any new numbers. Do not sum, subtract, multiply, divide, average, or project any numbers.
5. Do not use numbered lists (such as "1.", "2.", "3.") to avoid generating extraneous numbers. Use bullet points ("-") or narrative paragraphs instead.
6. Present the facts clearly, professionally, and faithfully to the source data.
"""


# ---------------------------------------------------------------------------
# Unit Conversions Registry
# ---------------------------------------------------------------------------

# Multipliers and conversion factors relative to the dimension's base unit.
UNIT_CONVERSIONS: Dict[str, Dict[str, float]] = {
    "mass": {
        # Base unit: kg
        "kg": 1.0,
        "kgs": 1.0,
        "kilogram": 1.0,
        "kilograms": 1.0,
        "g": 0.001,
        "gram": 0.001,
        "grams": 0.001,
        "t": 1000.0,
        "ton": 1000.0,
        "tons": 1000.0,
        "tonne": 1000.0,
        "tonnes": 1000.0,
        "metric ton": 1000.0,
        "metric tons": 1000.0,
        "metric tonne": 1000.0,
        "metric tonnes": 1000.0,
        "kt": 1_000_000.0,
        "kiloton": 1_000_000.0,
        "kilotonne": 1_000_000.0,
        "kilotons": 1_000_000.0,
        "kilotonnes": 1_000_000.0,
    },
    "energy": {
        # Base unit: kWh
        "wh": 0.001,
        "watt-hour": 0.001,
        "watt-hours": 0.001,
        "kwh": 1.0,
        "kw-h": 1.0,
        "kilowatt-hour": 1.0,
        "kilowatt-hours": 1.0,
        "kilowatt-hr": 1.0,
        "kilowatt-hrs": 1.0,
        "mwh": 1000.0,
        "mw-h": 1000.0,
        "megawatt-hour": 1000.0,
        "megawatt-hours": 1000.0,
        "gwh": 1_000_000.0,
        "gigawatt-hour": 1_000_000.0,
        "gigawatt-hours": 1_000_000.0,
    },
    "power": {
        # Base unit: kW
        "w": 0.001,
        "watt": 0.001,
        "watts": 0.001,
        "kw": 1.0,
        "kilowatt": 1.0,
        "kilowatts": 1.0,
        "mw": 1000.0,
        "megawatt": 1000.0,
        "megawatts": 1000.0,
    },
    "multiplier": {
        # Base multiplier: 1.0
        "k": 1000.0,
        "thousand": 1000.0,
        "thousands": 1000.0,
        "m": 1_000_000.0,
        "million": 1_000_000.0,
        "millions": 1_000_000.0,
        "b": 1_000_000_000.0,
        "billion": 1_000_000_000.0,
        "billions": 1_000_000_000.0,
    },
    "distance": {
        # Base unit: km
        "km": 1.0,
        "kms": 1.0,
        "kilometer": 1.0,
        "kilometers": 1.0,
        "kilometre": 1.0,
        "kilometres": 1.0,
        "m": 0.001,
        "meter": 0.001,
        "meters": 0.001,
        "metre": 0.001,
        "metres": 0.001,
        "miles": 1.60934,
        "mile": 1.60934,
        "mi": 1.60934,
    },
    "time": {
        # Base unit: year
        "year": 1.0,
        "years": 1.0,
        "yr": 1.0,
        "yrs": 1.0,
        "month": 1.0 / 12.0,
        "months": 1.0 / 12.0,
        "mo": 1.0 / 12.0,
    },
}

# Unit alias lookup: maps normalized unit string to (dimension, factor)
UNIT_LOOKUP: Dict[str, Tuple[str, float]] = {}
for dim, table in UNIT_CONVERSIONS.items():
    for u_name, factor in table.items():
        UNIT_LOOKUP[u_name.lower()] = (dim, factor)


# ---------------------------------------------------------------------------
# UnsupportedNumber Data Structure
# ---------------------------------------------------------------------------

class UnsupportedNumber(str):
    """
    Represents an unsupported or hallucinated number extracted from text.
    Subclasses str for 100% backward compatibility, while supporting rich
    equality comparisons against int, float, and formatted strings.
    """
    def __new__(
        cls,
        text_val: str,
        raw: str = "",
        value: float = 0.0,
        unit: Optional[str] = None,
        currency: Optional[str] = None,
        start: int = -1,
        end: int = -1,
    ):
        obj = super().__new__(cls, text_val)
        obj.raw = raw or text_val
        obj.value = value
        obj.unit = unit or ""
        obj.currency = currency or ""
        obj.start = start
        obj.end = end
        return obj

    def __eq__(self, other: Any) -> bool:
        if super().__eq__(other):
            return True
        if isinstance(other, (int, float)):
            return math.isclose(self.value, float(other), rel_tol=1e-3, abs_tol=1e-4)
        if isinstance(other, str):
            clean_other = other.replace(",", "").strip()
            clean_self = str(self).replace(",", "").strip()
            if clean_self == clean_other:
                return True
            try:
                val = float(clean_other)
                return math.isclose(self.value, val, rel_tol=1e-3, abs_tol=1e-4)
            except ValueError:
                pass
            if self.raw.strip().lower() == other.strip().lower():
                return True
            stripped_other = other.strip().lstrip("£$€₹").rstrip("%").strip()
            if stripped_other == clean_self:
                return True
        return False

    def __hash__(self) -> int:
        return super().__hash__()

    def __repr__(self) -> str:
        return f"UnsupportedNumber({str(self)!r}, raw={self.raw!r}, value={self.value})"


# ---------------------------------------------------------------------------
# Regex-Based Extraction
# ---------------------------------------------------------------------------

# Preprocessing: mask chemical formulas and common scientific notation where
# numbers are part of chemical identity rather than quantitative values.
CHEMICAL_FORMULA_PATTERN = re.compile(
    r"\bCO[2₂]e?\b|\bH2O\b|\bCH4\b|\bNOx\b",
    re.IGNORECASE
)

# Number extraction regex:
# Captures optional currency symbol, the numeric core (with comma separators or decimals),
# and optional unit/scale suffix.
NUMBER_EXTRACTION_PATTERN = re.compile(
    r"(?:(?<=\s)|(?<=^)|(?<=[(‘\"“\[/\-–—#]))"
    r"([£$€₹]?)\s*"
    r"([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[+-]?\.\d+)"
    r"\s*"
    r"(%|m²|m2|m³|m3|sqm|sqft|tonnes?|tons?|t|kg|kgs|kilograms?|grams?|g|kwh|kw-h|mwh|mw-h|gwh|wh|kw|mw|w|k|m|b|years?|yrs?|months?|mo|kms?|kilometers?|kilometres?|miles?|mi)?"
    r"(?=[.,;:!?)’\"”\]/\s\-–—]|$)",
    re.IGNORECASE
)


def preprocess_text_for_numbers(text: str) -> str:
    """
    Substitutes chemical symbols like CO2, CO2e, CO₂e with whitespace
    so their subscript '2' is not misconstrued as a numeric quantity.
    """
    return CHEMICAL_FORMULA_PATTERN.sub(lambda m: " " * len(m.group(0)), text)


def extract_numbers(text: str) -> List[Dict[str, Any]]:
    """
    Extracts every number from text using regex.
    Returns a list of dicts with keys:
      - 'raw': original matched substring (e.g., '1.2 t', '1,200 kg', '84%', '£350,000')
      - 'text_num': numeric part as string ('1.2', '1200', '84')
      - 'value': float value
      - 'unit': normalized unit string or empty
      - 'currency': currency symbol or empty
      - 'start': start index in original text
      - 'end': end index in original text
    """
    cleaned = preprocess_text_for_numbers(text)
    results = []

    for match in NUMBER_EXTRACTION_PATTERN.finditer(cleaned):
        curr, num_str, unit_str = match.groups()
        curr = (curr or "").strip()
        unit_str = (unit_str or "").strip().lower()

        # Clean number string (strip commas)
        clean_num = num_str.replace(",", "").strip()
        try:
            val = float(clean_num)
        except ValueError:
            continue

        start, end = match.span()
        raw_token = text[start:end].strip()

        results.append({
            "raw": raw_token,
            "text_num": num_str,
            "value": val,
            "unit": unit_str,
            "currency": curr,
            "start": start,
            "end": end,
        })

    return results


# ---------------------------------------------------------------------------
# Value Candidate Expansion & Unit Conversions
# ---------------------------------------------------------------------------

def expand_candidate_values(
    val: float,
    unit: Optional[str] = None,
    currency: Optional[str] = None
) -> Set[float]:
    """
    Expands a (val, unit) pair into all valid numeric representations across
    unit conversions, percentages, and scaling multipliers.
    E.g.:
      - 1.2 t -> {1.2, 1200.0, 1200000.0} (tonnes, kg, g)
      - 1200 kg -> {1200.0, 1.2, 1200000.0}
      - 84% -> {84.0, 0.84}
      - 350k -> {350.0, 350000.0}
    """
    candidates = {round(val, 6)}
    u = (unit or "").lower().strip()

    # Multipliers (k, m, b)
    if u in UNIT_CONVERSIONS["multiplier"]:
        mult = UNIT_CONVERSIONS["multiplier"][u]
        candidates.add(round(val * mult, 6))

    # Percentages
    if u in ("%", "percent", "pct"):
        candidates.add(round(val / 100.0, 6))
        candidates.add(round(val, 6))
    elif not u:
        # If no unit is specified, could be decimal or integer percentage
        if 0.0 <= val <= 1.0:
            candidates.add(round(val * 100.0, 6))
        if 0.0 <= val <= 100.0:
            candidates.add(round(val / 100.0, 6))

    # Unit Dimensions (mass, energy, power, distance, time)
    if u in UNIT_LOOKUP:
        dim, unit_factor = UNIT_LOOKUP[u]
        base_val = val * unit_factor
        candidates.add(round(base_val, 6))
        for other_unit, other_factor in UNIT_CONVERSIONS[dim].items():
            equiv = base_val / other_factor
            candidates.add(round(equiv, 6))

    return candidates


# ---------------------------------------------------------------------------
# Payload Inspection
# ---------------------------------------------------------------------------

def extract_payload_data(payload: Any) -> Tuple[Set[float], Set[str]]:
    """
    Recursively inspects a payload (dict, list, primitive) to extract:
    1. A set of allowable numerical values (including unit conversions & % forms)
    2. A set of raw token strings (identifiers, date segments, code strings)
    """
    allowed_numbers: Set[float] = set()
    allowed_tokens: Set[str] = set()

    def _traverse(obj: Any, key_context: str = ""):
        if obj is None:
            return

        # Booleans are not treated as numbers (True != 1, False != 0)
        if isinstance(obj, bool):
            return

        if isinstance(obj, (int, float)):
            f_val = float(obj)
            allowed_numbers.add(round(f_val, 6))

            # If field name gives unit context (e.g. estimated_reduction_kg: 1200)
            inferred_unit = None
            for u in ("kg", "t", "tonnes", "kwh", "mwh", "kw", "mw", "pct"):
                if key_context.lower().endswith(f"_{u}") or key_context.lower().endswith(f"_{u}s"):
                    inferred_unit = u
                    break

            for cand in expand_candidate_values(f_val, inferred_unit):
                allowed_numbers.add(cand)

            # Integer string token
            if isinstance(obj, int) or f_val.is_integer():
                allowed_tokens.add(str(int(f_val)))
            allowed_tokens.add(str(obj))

        elif isinstance(obj, str):
            allowed_tokens.add(obj.strip())
            # Extract any numbers from string payload fields (e.g. "1200 kg", "£350,000", "2-5%")
            extracted = extract_numbers(obj)
            for item in extracted:
                for cand in expand_candidate_values(item["value"], item["unit"], item["currency"]):
                    allowed_numbers.add(cand)
                allowed_tokens.add(item["text_num"])
                if item["value"].is_integer():
                    allowed_tokens.add(str(int(item["value"])))

            # Also extract alphanumeric sub-tokens (e.g. '10001' from 'C10001')
            digits = re.findall(r"\d+", obj)
            for d in digits:
                allowed_tokens.add(d)
                try:
                    allowed_numbers.add(float(d))
                except ValueError:
                    pass

        elif isinstance(obj, dict):
            for k, v in obj.items():
                _traverse(v, key_context=str(k))
                # Keys might also have identifiers
                _traverse(k, key_context="")

        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                _traverse(item, key_context=key_context)

    _traverse(payload)
    return allowed_numbers, allowed_tokens


# ---------------------------------------------------------------------------
# validate(text: str, payload: dict) -> list
# ---------------------------------------------------------------------------

def validate(text: str, payload: dict) -> List[UnsupportedNumber]:
    """
    Validates that every number present in the LLM's text reply is grounded
    in the source payload.

    Args:
        text: The LLM text output to validate.
        payload: The source structured data dictionary.

    Returns:
        A list of UnsupportedNumber instances (str-compatible) representing
        any unsupported or invented numbers found in the text.
    """
    if not text:
        return []

    allowed_numbers, allowed_tokens = extract_payload_data(payload)
    extracted_text_numbers = extract_numbers(text)
    unsupported_numbers: List[UnsupportedNumber] = []

    for item in extracted_text_numbers:
        val = item["value"]
        unit = item["unit"]
        curr = item["currency"]
        raw = item["raw"]
        clean_num_str = item["text_num"].replace(",", "")

        # Check 1: Direct token match in payload strings/IDs
        if clean_num_str in allowed_tokens or (val.is_integer() and str(int(val)) in allowed_tokens):
            continue

        # Check 2: Direct or expanded candidate match against allowed payload numbers
        text_candidates = expand_candidate_values(val, unit, curr)

        matched = False
        for cand in text_candidates:
            # Check against allowed numbers with floating point tolerance
            for p_num in allowed_numbers:
                if math.isclose(cand, p_num, rel_tol=1e-3, abs_tol=1e-4):
                    matched = True
                    break
            if matched:
                break

        if not matched:
            # Display representation: prefer raw token or clean number
            display_val = clean_num_str
            unsupported_obj = UnsupportedNumber(
                text_val=display_val,
                raw=raw,
                value=val,
                unit=unit,
                currency=curr,
                start=item["start"],
                end=item["end"],
            )
            unsupported_numbers.append(unsupported_obj)

    return unsupported_numbers


# ---------------------------------------------------------------------------
# explain(payload: dict) -> str
# ---------------------------------------------------------------------------

def _call_gemini_api(api_key: str, system_prompt: str, user_prompt: str, model: str = "gemini-1.5-flash") -> str:
    """Calls Gemini REST API using urllib."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.0}
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_openai_api(api_key: str, system_prompt: str, user_prompt: str, model: str = "gpt-4o-mini") -> str:
    """Calls OpenAI REST API using urllib."""
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def _format_grounded_fallback_explanation(payload: dict) -> str:
    """
    Built-in reference generator that faithfully follows all 4 grounding rules:
    1. Uses ONLY numbers explicitly present in the payload.
    2. Explicitly labels estimates as estimates.
    3. Outputs 'not available' when a payload field is null.
    4. Never computes, calculates, or derives new numbers.
    """
    lines = []

    # Customer and Opportunity
    cust_id = payload.get("customer_id")
    opp = payload.get("opportunity")
    cust_str = f"Customer {cust_id}" if cust_id is not None else "Customer"
    opp_str = str(opp).replace("_", " ").title() if opp is not None else "Green Opportunity"
    lines.append(f"Sustainability Insight for {cust_str}: {opp_str}.")

    # Propensity & Confidence
    propensity = payload.get("propensity")
    confidence = payload.get("confidence")
    if propensity is not None:
        lines.append(f"- Model Propensity: {propensity}")
    else:
        lines.append("- Model Propensity: not available")

    if confidence is not None:
        lines.append(f"- Model Confidence: {confidence}")
    else:
        lines.append("- Model Confidence: not available")

    # Reason codes / Evidence
    reason_codes = payload.get("reason_codes")
    if reason_codes is not None:
        if isinstance(reason_codes, list):
            reasons_str = ", ".join(str(r).replace("_", " ").title() for r in reason_codes)
        else:
            reasons_str = str(reason_codes)
        lines.append(f"- Identified Factors: {reasons_str}")
    else:
        lines.append("- Identified Factors: not available")

    # Financial / Operational Metrics (use raw payload values directly, no math)
    fuel_spend = payload.get("annual_fuel_spend")
    if fuel_spend is not None:
        lines.append(f"- Recorded Annual Fuel Spend: £{fuel_spend}")
    elif "annual_fuel_spend" in payload:
        lines.append("- Recorded Annual Fuel Spend: not available")

    mileage = payload.get("annual_mileage")
    if mileage is not None:
        lines.append(f"- Recorded Annual Mileage: {mileage}")
    elif "annual_mileage" in payload:
        lines.append("- Recorded Annual Mileage: not available")

    # Baseline Consumption
    baseline_elec = payload.get("baseline_electricity_kwh")
    if baseline_elec is not None:
        lines.append(f"- Baseline Electricity Consumption: {baseline_elec} kWh")
    elif "baseline_electricity_kwh" in payload:
        lines.append("- Baseline Electricity Consumption: not available")

    baseline_gas = payload.get("baseline_gas_kwh")
    if baseline_gas is not None:
        lines.append(f"- Baseline Gas Consumption: {baseline_gas} kWh")
    elif "baseline_gas_kwh" in payload:
        lines.append("- Baseline Gas Consumption: not available")

    # Sustainability Impact (Explicitly labeled as an estimate)
    reduction = payload.get("estimated_annual_reduction_kg") or payload.get("estimated_annual_reduction")
    unit = payload.get("unit", "kg CO2e")
    method = payload.get("method")
    if reduction is not None:
        method_note = f" (calculated via {method})" if method else ""
        lines.append(f"- Potential Sustainability Impact: estimated annual reduction of {reduction} {unit}{method_note}")
    elif "estimated_annual_reduction_kg" in payload or "estimated_annual_reduction" in payload:
        lines.append("- Potential Sustainability Impact: not available")

    # Property Value Impact (Indicative estimate range)
    prop_val = payload.get("property_value")
    if prop_val is not None:
        lines.append(f"- Current Property Valuation: £{prop_val}")
    elif "property_value" in payload:
        lines.append("- Current Property Valuation: not available")

    uplift = payload.get("indicative_uplift") or payload.get("uplift_range")
    if uplift is not None:
        lines.append(f"- Indicative Uplift Range: {uplift} (indicative estimate)")
    elif "indicative_uplift" in payload or "uplift_range" in payload:
        lines.append("- Indicative Uplift Range: not available")

    potential_val = payload.get("potential_value")
    if potential_val is not None:
        lines.append(f"- Estimated Potential Property Value: {potential_val} (indicative estimate)")
    elif "potential_value" in payload:
        lines.append("- Estimated Potential Property Value: not available")

    # Cutoff date / Timestamp
    timestamp = payload.get("data_cutoff_date") or payload.get("timestamp")
    if timestamp is not None:
        lines.append(f"- Data Cutoff Date: {timestamp}")
    elif "data_cutoff_date" in payload or "timestamp" in payload:
        lines.append("- Data Cutoff Date: not available")

    # Notes / Other optional fields
    for k, v in payload.items():
        if k not in (
            "customer_id", "opportunity", "propensity", "confidence", "reason_codes",
            "annual_fuel_spend", "annual_mileage", "baseline_electricity_kwh", "baseline_gas_kwh",
            "estimated_annual_reduction_kg", "estimated_annual_reduction", "unit", "method",
            "property_value", "indicative_uplift", "uplift_range", "potential_value",
            "data_cutoff_date", "timestamp"
        ):
            field_name = k.replace("_", " ").title()
            if v is None:
                lines.append(f"- {field_name}: not available")
            else:
                lines.append(f"- {field_name}: {v}")

    return "\n".join(lines)


def explain(
    payload: dict,
    llm_fn: Optional[Callable[[str, str], str]] = None,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Generates a customer-facing explanation grounded strictly in the source payload.

    Enforces the following rules via system prompt:
    1. Use ONLY numbers explicitly present in the payload.
    2. Explicitly label any estimates as estimates.
    3. Output "not available" when a payload field is null.
    4. Never compute, calculate, or derive any new numbers.

    Args:
        payload: Structured customer insight data dictionary.
        llm_fn: Optional custom LLM caller taking (system_prompt, user_prompt) -> str.
        api_key: Optional API key for Gemini / OpenAI. If not specified, checks env vars.
        provider: 'gemini', 'openai', or None (auto-detect).
        model: Model name to use.

    Returns:
        The generated explanation string.
    """
    system_prompt = GROUNDING_SYSTEM_PROMPT
    user_prompt = (
        f"Here is the customer data payload:\n"
        f"{json.dumps(payload, indent=2)}\n\n"
        f"Please provide a customer-friendly plain-language explanation following all grounding rules."
    )

    # 1. Custom LLM function hook
    if llm_fn is not None:
        return llm_fn(system_prompt, user_prompt)

    # 2. Check Gemini
    gemini_key = api_key if provider == "gemini" else (api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if gemini_key and (provider in (None, "gemini")):
        try:
            return _call_gemini_api(
                api_key=gemini_key,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model or "gemini-1.5-flash"
            )
        except Exception as e:
            print(f"[explain] Gemini API call failed: {e}. Falling back to reference generator.")

    # 3. Check OpenAI
    openai_key = api_key if provider == "openai" else (api_key or os.environ.get("OPENAI_API_KEY"))
    if openai_key and (provider in (None, "openai")):
        try:
            return _call_openai_api(
                api_key=openai_key,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model or "gpt-4o-mini"
            )
        except Exception as e:
            print(f"[explain] OpenAI API call failed: {e}. Falling back to reference generator.")

    # 4. Built-in strictly grounded reference generator
    return _format_grounded_fallback_explanation(payload)


# ---------------------------------------------------------------------------
# Hallucination Simulator (for Testing & Verification)
# ---------------------------------------------------------------------------

def simulate_hallucination(base_text: str, injected_claims: Optional[List[str]] = None) -> str:
    """
    Deliberately injects ungrounded numerical claims into a text to simulate
    LLM hallucinations for validation testing.
    """
    if injected_claims is None:
        injected_claims = [
            "We also project an additional bonus saving of 999 kg CO2e.",
            "You are eligible for a special £450 incentive at 5.5% APR.",
        ]
    injection = " ".join(injected_claims)
    return f"{base_text}\n\n[Injected Hallucinations]: {injection}"
