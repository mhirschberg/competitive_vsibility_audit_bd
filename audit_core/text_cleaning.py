"""Pure text cleanup shared by provider validation and report finalization."""

import re


def remove_ai_boilerplate(text):
    """Remove AI-interface boilerplate and unwrap captured Markdown reports."""
    if not isinstance(text, str):
        return ""

    text = text.strip()
    if not text:
        return ""

    lines = text.splitlines()

    # ChatGPT scraper output can wrap a whole response in one Markdown item.
    first_nonempty_index = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )
    if first_nonempty_index is not None:
        first_line = lines[first_nonempty_index]
        if re.match(
            r"^\s*[*+-]\s+Competitive Visibility Audit\s*$",
            first_line,
            flags=re.IGNORECASE,
        ):
            lines[first_nonempty_index] = "Competitive Visibility Audit"
            for index in range(first_nonempty_index + 1, len(lines)):
                if lines[index].startswith("    "):
                    lines[index] = lines[index][4:]

    exact_unwanted = {
        "log in",
        "login",
        "sign up",
        "sign up for free",
        "log insign up for free",
    }
    unwanted_prefixes = (
        "log in for more personalized",
        "if you want",
        "if useful",
        "would you like",
        "below is a professional audit",
        "below is the competitive visibility audit",
        "below is the requested audit",
        "here is the requested audit",
        "here's the requested audit",
    )

    cleaned_lines = []
    for line in lines:
        normalized = re.sub(r"\s+", " ", line).strip().lower()
        normalized_for_check = normalized.lstrip("•*-–—>#_ ")
        if normalized_for_check in exact_unwanted:
            continue
        if any(normalized_for_check.startswith(prefix) for prefix in unwanted_prefixes):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    cleaned = re.sub(
        r"^Competitive Visibility Audit\s*\n=+\s*$",
        "# Competitive Visibility Audit",
        cleaned,
        count=1,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    cleaned = re.sub(
        r"^# Competitive Visibility Audit\s*\n\s*# Competitive Visibility Audit",
        "# Competitive Visibility Audit",
        cleaned,
        count=1,
        flags=re.IGNORECASE,
    )
    return cleaned
