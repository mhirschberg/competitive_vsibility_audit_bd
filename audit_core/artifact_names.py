"""Stable, readable names for user-facing audit downloads."""

from datetime import datetime, timezone
import unicodedata


REPORT_SUFFIX = "competitive_visibility_audit"
REPORT_EXTENSIONS = frozenset({"pdf", "md", "json", "zip"})


def _name_part(value, limit):
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    characters = [character if character.isalnum() else "-" for character in normalized]
    return "-".join(filter(None, "".join(characters).split("-")))[:limit].strip("-")


def audit_export_prefix(run_timestamp, company, focus, country):
    """Use the original run timestamp so resumed exports keep one identity."""
    if isinstance(run_timestamp, str):
        run_timestamp = datetime.fromisoformat(run_timestamp.replace("Z", "+00:00"))
    if run_timestamp.tzinfo is None:
        run_timestamp = run_timestamp.replace(tzinfo=timezone.utc)
    stamp = run_timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d_%H%M%S%f")
    company_part = _name_part(company, 32) or "company"
    focus_part = _name_part(focus, 40)
    country_part = _name_part(country, 4).upper() or "XX"
    parts = [stamp, company_part]
    if focus_part:
        parts.append(focus_part)
    parts.append(country_part)
    return "_".join(parts)


def report_filename(prefix, extension):
    if extension not in REPORT_EXTENSIONS:
        raise ValueError(f"Unsupported report extension: {extension}")
    return f"{prefix}_{REPORT_SUFFIX}.{extension}"


def is_final_report_json(name):
    """Recognize new and legacy JSON names without matching stage snapshots."""
    return str(name).endswith(f"_{REPORT_SUFFIX}.json")
