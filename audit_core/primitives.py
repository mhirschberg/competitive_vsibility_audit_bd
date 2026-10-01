"""Pure normalization helpers shared by the service and standalone notebook."""

import re


def ensure_string_list(value):
    if value is None:
        return []

    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []

    if isinstance(value, list):
        results = []

        for item in value:
            if item is None:
                continue

            item = str(item).strip()

            if item:
                results.append(item)

        return results

    return [str(value).strip()]


def normalize_boolean(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "yes",
            "1",
        }

    return bool(value)


def normalize_confidence(value):
    try:
        value = float(value)

        if 1 < value <= 100:
            value = value / 100

        return max(
            0.0,
            min(1.0, value),
        )

    except (TypeError, ValueError):
        return 0.0


def shorten(
    value,
    max_length,
):
    value = str(value or "").strip()

    if len(value) <= max_length:
        return value

    return (
        value[:max_length - 3]
        .rstrip()
        + "..."
    )


def slugify(value):
    value = re.sub(
        r"[^a-zA-Z0-9]+",
        "-",
        str(value or "").lower(),
    )

    return value.strip("-") or "audit"


def format_duration(seconds):
    """Format elapsed seconds consistently in hosted and notebook progress."""
    seconds = float(seconds or 0)
    if seconds < 60:
        return f"{seconds:.1f}s"

    minutes = int(seconds // 60)
    remaining = int(seconds % 60)
    return f"{minutes}m {remaining}s"
