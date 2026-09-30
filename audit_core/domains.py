"""Domain normalization shared by the service and standalone notebook."""

from urllib.parse import urlparse, urlunparse

import tldextract


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
