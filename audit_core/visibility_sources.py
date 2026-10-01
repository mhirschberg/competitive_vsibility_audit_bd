"""Classify and deduplicate citations in measured AI answers.

Redirect resolution is an optional caller-supplied port: a report can be built
from saved answers without making a new network request.
"""

import re
from urllib.parse import urlparse

# SERVICE-ONLY-IMPORTS: start
from .domains import canonical_source_url, get_root_domain
# SERVICE-ONLY-IMPORTS: end


SOCIAL_DOMAINS = {
    "linkedin.com", "reddit.com", "youtube.com", "facebook.com",
    "instagram.com", "x.com", "twitter.com", "medium.com", "quora.com",
}
RETAILER_DOMAINS = {
    "amazon.com", "walmart.com", "target.com", "sephora.com",
    "ulta.com", "ebay.com", "etsy.com", "medicalexpo.com",
    "directindustry.com",
}
SCIENTIFIC_DOMAINS = {
    "nature.com", "sciencedirect.com", "springer.com", "wiley.com",
    "nih.gov", "bmj.com", "thelancet.com", "nejm.org",
}
MARKET_RESEARCH_DOMAINS = {
    "tracxn.com", "marketsandmarkets.com", "researchandmarkets.com",
    "mordorintelligence.com", "verifiedmarketresearch.com",
    "sphericalinsights.com", "delveinsight.com",
    "fortunebusinessinsights.com", "grandviewresearch.com",
}
KNOWN_PUBLISHERS = {
    "reviewofophthalmology.com", "forbes.com", "techcrunch.com",
    "businessinsider.com", "allure.com", "vogue.com", "byrdie.com",
}
OFFICIAL_PATH_TERMS = (
    "/product", "/products", "/professional", "/professionals",
    "/media-release", "/press-release", "/press-releases", "/investor",
    "/news-release", "/our-products",
)
MARKET_RESEARCH_TITLE_PATTERNS = (
    r"\bmarket size\b", r"\bmarket report\b", r"\bmarket forecast\b",
    r"\bindustry report\b", r"\btop \d+ companies\b",
    r"\bleading companies\b", r"\bcompanies in\b",
)
VISIBILITY_SOURCE_ENGINE_NAMES = (
    ("google_ai_mode", "Google AI Mode"), ("chatgpt", "ChatGPT"),
    ("gemini", "Gemini"), ("copilot", "Copilot"),
)


def classify_visibility_source(final_url, title, audited_domains):
    parsed = urlparse(final_url)
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    root_domain = get_root_domain(hostname)
    path = (parsed.path or "").lower()
    title_lower = (title or "").lower()

    if root_domain in audited_domains:
        return "Official audited brand"
    if root_domain.endswith(".gov") or hostname.endswith(".gov"):
        return "Government or regulator"
    if root_domain.endswith(".edu") or hostname.endswith(".edu"):
        return "Academic or educational"
    if root_domain in SCIENTIFIC_DOMAINS or any(
        hostname.endswith("." + domain) for domain in SCIENTIFIC_DOMAINS
    ):
        return "Scientific or professional"
    if root_domain in SOCIAL_DOMAINS:
        return "Social or community"
    if root_domain in RETAILER_DOMAINS:
        return "Retailer or marketplace"
    if root_domain in MARKET_RESEARCH_DOMAINS or any(
        re.search(pattern, title_lower)
        for pattern in MARKET_RESEARCH_TITLE_PATTERNS
    ):
        return "Market research or directory"
    if any(term in path for term in OFFICIAL_PATH_TERMS):
        return "Official company or product"
    if root_domain in KNOWN_PUBLISHERS:
        return "Publisher or editorial"
    return "Publisher or other source"


def collect_visibility_sources_core(
    visibility, max_per_engine=10, *, resolve_google_goto_url=None,
    is_google_goto_url=None,
):
    """Replicate the notebook's base collection order and per-engine limit."""
    collected = []
    seen = set()
    audited_domains = visibility.get("audited_domains", {})

    for engine, display_name in VISIBILITY_SOURCE_ENGINE_NAMES:
        if engine not in visibility["engines"]:
            continue
        result = visibility["engines"].get(engine, {})
        engine_count = 0
        for citation in result.get("citations", []):
            if not isinstance(citation, dict):
                continue
            raw_url = str(
                citation.get("url") or citation.get("link") or ""
            ).strip()
            if not raw_url:
                continue
            resolved_url = (
                resolve_google_goto_url(raw_url)
                if resolve_google_goto_url is not None else ""
            )
            final_url = resolved_url or raw_url
            if is_google_goto_url is not None and is_google_goto_url(final_url):
                continue
            canonical_url = canonical_source_url(final_url)
            if not canonical_url or canonical_url in seen:
                continue
            seen.add(canonical_url)
            title = str(
                citation.get("title") or citation.get("name")
                or citation.get("domain") or "Untitled source"
            ).strip()
            collected.append({
                "engine": display_name,
                "title": title,
                "url": final_url,
                "canonical_url": canonical_url,
                "domain": get_root_domain(final_url),
                "source_type": classify_visibility_source(
                    final_url, title, audited_domains,
                ),
            })
            engine_count += 1
            if engine_count >= max_per_engine:
                break

    return collected


def is_unresolved_google_interface_url(value):
    value = str(value or "").strip()
    if not value:
        return True
    try:
        parsed = urlparse(value)
        hostname = (parsed.hostname or "").lower().removeprefix("www.")
        path = (parsed.path or "").lower()
        return hostname == "google.com" and path.startswith(
            ("/goto", "/searchviewer", "/search")
        )
    except Exception:
        return False


def collect_visibility_sources_service(
    visibility, max_per_engine=10, *, resolve_google_goto_url=None,
    is_google_goto_url=None,
):
    """The effective collector, including the notebook's quality filter."""
    sources = collect_visibility_sources_core(
        visibility, max_per_engine,
        resolve_google_goto_url=resolve_google_goto_url,
        is_google_goto_url=is_google_goto_url,
    )
    return [
        source for source in sources
        if not is_unresolved_google_interface_url(
            source.get("url") or source.get("canonical_url")
        )
    ]
