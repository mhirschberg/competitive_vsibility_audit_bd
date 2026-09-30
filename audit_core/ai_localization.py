"""Country targeting and answer-localization policy shared with the notebook."""

import json
import re

# SERVICE-ONLY-IMPORTS: start
from .brightdata_transport import BrightDataAPIError
# SERVICE-ONLY-IMPORTS: end

STRICT_AI_COUNTRY_VALIDATION = True

AI_LOCALIZATION_RACE_ATTEMPTS = 2

AI_COUNTRY_DETAILS = {'US': {'name': 'United States',
        'aliases': ('United States',
                    'United States market',
                    'U.S.',
                    'USA',
                    'American market',
                    'US market')},
 'DE': {'name': 'Germany',
        'aliases': ('Germany', 'German', 'German market', 'Deutschland')},
 'GB': {'name': 'United Kingdom',
        'aliases': ('United Kingdom', 'UK market', 'British market', 'Britain')},
 'UK': {'name': 'United Kingdom',
        'aliases': ('United Kingdom', 'UK market', 'British market', 'Britain')},
 'FR': {'name': 'France', 'aliases': ('France', 'French', 'French market')},
 'IT': {'name': 'Italy', 'aliases': ('Italy', 'Italian', 'Italian market')},
 'ES': {'name': 'Spain', 'aliases': ('Spain', 'Spanish', 'Spanish market')},
 'NL': {'name': 'Netherlands', 'aliases': ('Netherlands', 'Dutch', 'Dutch market')},
 'BE': {'name': 'Belgium', 'aliases': ('Belgium', 'Belgian', 'Belgian market')},
 'AT': {'name': 'Austria', 'aliases': ('Austria', 'Austrian', 'Austrian market')},
 'CH': {'name': 'Switzerland', 'aliases': ('Switzerland', 'Swiss', 'Swiss market')},
 'CA': {'name': 'Canada', 'aliases': ('Canada', 'Canadian', 'Canadian market')},
 'AU': {'name': 'Australia',
        'aliases': ('Australia', 'Australian', 'Australian market')},
 'JP': {'name': 'Japan', 'aliases': ('Japan', 'Japanese', 'Japanese market')},
 'IN': {'name': 'India', 'aliases': ('India', 'Indian', 'Indian market')},
 'BR': {'name': 'Brazil', 'aliases': ('Brazil', 'Brazilian', 'Brazilian market')},
 'MX': {'name': 'Mexico', 'aliases': ('Mexico', 'Mexican', 'Mexican market')},
 'SE': {'name': 'Sweden', 'aliases': ('Sweden', 'Swedish', 'Swedish market')},
 'NO': {'name': 'Norway', 'aliases': ('Norway', 'Norwegian', 'Norwegian market')},
 'DK': {'name': 'Denmark', 'aliases': ('Denmark', 'Danish', 'Danish market')},
 'FI': {'name': 'Finland', 'aliases': ('Finland', 'Finnish', 'Finnish market')},
 'PL': {'name': 'Poland', 'aliases': ('Poland', 'Polish', 'Polish market')},
 'PT': {'name': 'Portugal', 'aliases': ('Portugal', 'Portuguese', 'Portuguese market')},
 'IE': {'name': 'Ireland', 'aliases': ('Ireland', 'Irish', 'Irish market')},
 'IL': {'name': 'Israel', 'aliases': ('Israel', 'Israeli', 'Israeli market')},
 'SG': {'name': 'Singapore', 'aliases': ('Singapore', 'Singapore market')},
 'KR': {'name': 'South Korea',
        'aliases': ('South Korea', 'Korean', 'South Korean market')},
 'AE': {'name': 'United Arab Emirates',
        'aliases': ('United Arab Emirates', 'UAE', 'Emirati market')},
 'SA': {'name': 'Saudi Arabia', 'aliases': ('Saudi Arabia', 'Saudi', 'Saudi market')},
 'ZA': {'name': 'South Africa',
        'aliases': ('South Africa', 'South African', 'South African market')},
 'NZ': {'name': 'New Zealand', 'aliases': ('New Zealand', 'New Zealand market')}}

GEMINI_PROMPT_ONLY_COUNTRIES = {
    'AD',
    'AL',
    'AT',
    'BA',
    'BE',
    'BG',
    'CH',
    'CY',
    'CZ',
    'DE',
    'DK',
    'EE',
    'ES',
    'FI',
    'FR',
    'GB',
    'GR',
    'HR',
    'HU',
    'IE',
    'IS',
    'IT',
    'LI',
    'LT',
    'LU',
    'LV',
    'MC',
    'MD',
    'ME',
    'MK',
    'MT',
    'NL',
    'NO',
    'PL',
    'PT',
    'RO',
    'RS',
    'SE',
    'SI',
    'SK',
    'SM',
    'UA',
    'UK',
    'VA',
    'XK',
}

MARKET_LANGUAGE_BY_COUNTRY = {'US': 'English',
 'GB': 'English',
 'UK': 'English',
 'CA': 'English',
 'AU': 'English',
 'NZ': 'English',
 'IE': 'English',
 'DE': 'German',
 'AT': 'German',
 'CH': 'German',
 'FR': 'French',
 'BE': 'French or Dutch, as appropriate',
 'NL': 'Dutch',
 'IT': 'Italian',
 'ES': 'Spanish',
 'MX': 'Spanish',
 'PT': 'Portuguese',
 'BR': 'Portuguese',
 'PL': 'Polish',
 'CZ': 'Czech',
 'SK': 'Slovak',
 'SE': 'Swedish',
 'NO': 'Norwegian',
 'DK': 'Danish',
 'FI': 'Finnish',
 'JP': 'Japanese',
 'KR': 'Korean',
 'IN': 'English',
 'IL': 'Hebrew',
 'AE': 'Arabic or English, as appropriate',
 'SA': 'Arabic',
 'SG': 'English',
 'ZA': 'English'}


def normalize_ai_country_code(value):
    return str(value or "").strip().upper()


def country_details(country_code):
    code = normalize_ai_country_code(country_code)
    details = AI_COUNTRY_DETAILS.get(code)
    if details:
        return {
            "code": code,
            "name": details["name"],
            "aliases": tuple(details["aliases"]),
        }
    return {
        "code": code,
        "name": f"country {code}" if code else "the selected country",
        "aliases": (code,) if code else (),
    }


def normalize_market_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def answer_acknowledges_target_market(answer, details):
    normalized_answer = " " + normalize_market_text(answer) + " "
    matched_aliases = []
    for alias in details.get("aliases", ()):
        normalized_alias = normalize_market_text(alias)
        if normalized_alias and f" {normalized_alias} " in normalized_answer:
            matched_aliases.append(alias)
    return {
        "acknowledged": bool(matched_aliases),
        "matched_aliases": matched_aliases,
    }


def extract_reported_ai_country(record):
    if not isinstance(record, dict):
        return None
    values = [
        record.get("country"), record.get("country_code"),
        record.get("requested_country"), record.get("location_country"),
    ]
    input_value = record.get("input")
    if isinstance(input_value, dict):
        values.extend((input_value.get("country"), input_value.get("country_code")))
    for value in values:
        value = str(value or "").strip()
        if value:
            return value
    return None


def reported_country_matches_target(reported_country, details):
    if not reported_country:
        return None
    reported = normalize_market_text(reported_country)
    if reported == details["code"].lower():
        return True
    expected = {normalize_market_text(details["name"])}
    expected.update(normalize_market_text(value) for value in details.get("aliases", ()))
    return reported in expected


def strict_market_instruction(details):
    return f"""
TARGET MARKET — STRICT REQUIREMENT

Target country: {details["name"]} ({details["code"]}).

Evaluate the category from the perspective of a buyer physically
located in {details["name"]}. Prioritize brands, products, services,
providers, prices, availability, regulations, and sources that are
applicable to this specific country.

Do not silently substitute United States, United Kingdom, global, or
other-country results for the target market. If global information is
used, explicitly confirm that it applies to {details["name"]}.

State clearly in the answer that the evaluation is for the
{details["name"]} market. Keep the answer in English for consistent
comparison across audit runs.
""".strip()


def localized_visibility_prompt(base_prompt, details, max_length=4096):
    localized = base_prompt.rstrip() + "\n\n" + strict_market_instruction(details)
    if len(localized) > max_length:
        raise ValueError(
            f"Localized AI visibility prompt is too long: {len(localized)} characters."
        )
    return localized


def market_language(country_code):
    return MARKET_LANGUAGE_BY_COUNTRY.get(
        normalize_ai_country_code(country_code),
        "the primary local search language",
    )


def compact_market_instruction_core(details):
    language = market_language(details["code"])
    return (
        f"STRICT TARGET MARKET: {details['name']} ({details['code']}). "
        f"Use {details['name']}-specific availability, relevance, competitors, "
        f"and sources. Do not silently substitute US, UK, global, or "
        f"other-market results. Buyer search queries must be written in "
        f"{language}. Keep explanatory analysis in English."
    )


def localize_google_ai_prompt_core(prompt, details, max_length=4096):
    """Keep near-limit research prompts intact where possible."""
    prompt = str(prompt or "").strip()
    if not prompt or "STRICT TARGET MARKET:" in prompt:
        return prompt
    language = market_language(details["code"])
    instruction = compact_market_instruction_core(details)
    combined = instruction + "\n\n" + prompt
    if len(combined) <= max_length:
        return combined

    replacements = (
        ("Research the current market",
         f"Research the current {details['name']} market"),
        ("Analyze this current public website.",
         f"Analyze this website for the {details['name']} market."),
        ("Analyze the current public website",
         f"Analyze the website for the {details['name']} market"),
        ("Inspect the current public website",
         f"Inspect the website for the {details['name']} market"),
        ("A customer is researching this need:",
         f"A customer in {details['name']} ({details['code']}) is researching this need:"),
    )
    localized = prompt
    for old, new in replacements:
        if old in localized:
            localized = localized.replace(old, new, 1)
            break
    language_line = (
        f"\nBuyer search queries must use {language} for {details['name']}."
    )
    if "buyer" in localized.lower() and len(localized) + len(language_line) <= max_length:
        localized += language_line
    return localized[:max_length]


def country_payload_items(payload):
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("input"), list):
        return [item for item in payload["input"] if isinstance(item, dict)]
    return []


def set_payload_country(payload, country_code):
    """Normalize the legacy dataset field before engine-specific handling."""
    value = normalize_ai_country_code(country_code).lower()
    for item in country_payload_items(payload):
        item["country"] = value
    return payload


def clear_utility_country(result):
    """Utility transformations are not geographically measured searches."""
    for item in country_payload_items(result.get("payload")):
        item.pop("country", None)
    result["country_transport"] = "not_required"
    return result


def country_transport_mode(engine, country_code):
    code = normalize_ai_country_code(country_code)
    if str(engine or "").strip().lower() == "gemini" and code in GEMINI_PROMPT_ONLY_COUNTRIES:
        return "prompt_only"
    return "country_field_and_prompt" if code else "prompt_only"


def apply_compatible_country_payload(payload, engine, country_code):
    """Keep prompt targeting while omitting unsupported Gemini country fields."""
    engine = str(engine or "").strip().lower()
    code = normalize_ai_country_code(country_code)
    for item in country_payload_items(payload):
        if engine not in {"chatgpt", "gemini", "copilot"}:
            continue
        if code and country_transport_mode(engine, code) != "prompt_only":
            item["country"] = code
        else:
            item.pop("country", None)
    return payload


def annotate_country_transport(result, engine, country_code):
    code = normalize_ai_country_code(country_code)
    mode = country_transport_mode(engine, code)
    result["country_transport_mode"] = mode
    result["requested_country"] = code
    record = result.get("record")
    if isinstance(record, dict):
        localization = record.setdefault("_localization", {})
        localization["country_transport_mode"] = mode
        localization["requested_country"] = code
    return result


def assess_localized_answer(result, details, attempt, strict=True):
    answer = str(result.get("answer", "") or "")
    record = result.get("record")
    reported_country = extract_reported_ai_country(record)
    country_match = reported_country_matches_target(reported_country, details)
    acknowledgment = answer_acknowledges_target_market(answer, details)
    reasons = []
    if country_match is False:
        reasons.append(
            f"Scraper record reported {reported_country!r} instead of {details['code']}."
        )
    if strict and not acknowledgment["acknowledged"]:
        reasons.append(
            f"Answer did not explicitly acknowledge the {details['name']} market."
        )
    metadata = {
        "requested_country": details["code"],
        "requested_country_name": details["name"],
        "reported_country": reported_country,
        "country_verified": country_match,
        "market_acknowledged": acknowledgment["acknowledged"],
        "matched_market_aliases": acknowledgment["matched_aliases"],
        "localization_attempt": attempt,
        "strict_validation": strict,
    }
    return metadata, reasons


def race_localized_ai_visibility(
    client, engine, prompt, redundancy, timeout_seconds, *, race_once,
    details, attempts=AI_LOCALIZATION_RACE_ATTEMPTS,
    strict=STRICT_AI_COUNTRY_VALIDATION,
):
    """Retry a measured answer only when its target-market evidence fails."""
    failures = []
    for attempt in range(1, attempts + 1):
        result = race_once(client, engine, prompt, redundancy, timeout_seconds)
        if result.get("status") != "success":
            return result
        metadata, reasons = assess_localized_answer(result, details, attempt, strict)
        record = result.get("record")
        if not reasons:
            result.update(metadata)
            if isinstance(record, dict):
                record["_localization"] = metadata
            return result
        failures.append({
            **metadata,
            "engine": engine,
            "reasons": reasons,
            "winner_snapshot_id": result.get("winner_snapshot_id"),
        })
        client.log(
            f"{engine.title()} localization attempt {attempt} failed: "
            + "; ".join(reasons),
            "yellow",
        )
    raise BrightDataAPIError(
        f"{engine.title()} did not return a strictly localized answer for "
        f"{details['name']} after {attempts} three-snapshot race(s): "
        + json.dumps(failures, ensure_ascii=False)
    )
