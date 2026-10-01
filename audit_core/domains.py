"""Domain normalization shared by the service and standalone notebook."""

import re
from urllib.parse import urlparse, urlunparse

import tldextract


def extract_visible_url(value):
    """Extract a URL visible in plain text or a Markdown link."""
    value = str(value or "").strip()
    markdown_match = re.search(
        r"\[(https?://[^\]]+)\]" r"\([^)]+\)", value,
    )
    if markdown_match:
        value = markdown_match.group(1)

    url_match = re.search(r"https?://[^\s\])\"'>]+", value)
    if url_match:
        value = url_match.group(0)
    return value.rstrip(".,;:!?)]}")


def normalize_public_url(value):
    """Normalize a visible public URL while retaining its scheme and path."""
    value = extract_visible_url(value)
    if not value:
        value = str(value or "").strip()
    if not value:
        return ""
    if not value.lower().startswith(("http://", "https://")):
        value = f"https://{value}"

    parsed = urlparse(value)
    if not parsed.hostname:
        return ""
    scheme = parsed.scheme or "https"
    hostname = parsed.hostname.lower()
    path = parsed.path or "/"
    return f"{scheme}://{hostname}{path}"


def get_hostname(value):
    normalized = normalize_public_url(value)
    if not normalized:
        return ""
    return (urlparse(normalized).hostname or "").lower().removeprefix("www.")


def get_root_domain(value):
    if not value:
        return ""

    value = str(value).strip().lower()

    if "://" in value:
        hostname = urlparse(value).hostname or ""
    else:
        hostname = value.split("/")[0]

    hostname = hostname.removeprefix("www.")
    extracted = tldextract.extract(hostname)

    if not extracted.domain:
        return hostname

    if not extracted.suffix:
        return extracted.domain

    return f"{extracted.domain}.{extracted.suffix}"


def canonical_source_url(value):
    """Deduplicate citation URLs by removing query strings and fragments."""
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        parsed = urlparse(value)
        return urlunparse((
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "", "", "",
        ))
    except Exception:
        return value
