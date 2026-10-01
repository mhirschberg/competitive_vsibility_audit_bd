"""Tolerant parsing for structured answers returned by AI providers."""

import json
import re

from json_repair import repair_json


def clean_ai_json_text(text):
    text = str(text or "").strip()
    text = re.sub(
        r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE,
    )
    text = re.sub(r"\s*```\s*$", "", text)

    replacements = {
        r"\_": "_", r"\[": "[", r"\]": "]",
        r"\{": "{", r"\}": "}", r"\#": "#",
        r"\-": "-", r"\+": "+", r"\.": ".",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)

    text = re.sub(
        r"\[(https?://[^\]]+)\]" r"\([^)]+\)", r"\1", text,
    )
    return text.strip()


def parse_ai_json(text):
    """Parse a JSON object from plain, fenced, wrapped, or repairable output."""
    original_text = str(text or "").strip()
    if not original_text:
        raise ValueError("AI returned empty answer text.")

    cleaned = clean_ai_json_text(original_text)
    candidate_strings = [cleaned]
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        candidate_strings.insert(0, cleaned[first_brace:last_brace + 1])

    errors = []
    for candidate in candidate_strings:
        if not candidate.strip():
            continue

        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
            errors.append(
                "Standard JSON result was "
                f"{type(parsed).__name__}, not an object."
            )
        except Exception as exc:
            errors.append(f"Standard JSON: {exc}")

        try:
            repaired = repair_json(candidate, return_objects=True)
            if isinstance(repaired, dict):
                return repaired
            if isinstance(repaired, list):
                for item in repaired:
                    if isinstance(item, dict):
                        return item
            if isinstance(repaired, str) and repaired.strip():
                try:
                    reparsed = json.loads(repaired)
                    if isinstance(reparsed, dict):
                        return reparsed
                except Exception as exc:
                    errors.append(f"Repaired string JSON: {exc}")
        except Exception as exc:
            errors.append(f"JSON repair: {exc}")

    raise ValueError(
        "AI response could not be parsed as a JSON object.\n\n"
        f"Response preview:\n{original_text[:2500]}\n\n"
        "Parser errors:\n- " + "\n- ".join(errors[-6:])
    )
