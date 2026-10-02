"""Pure market-scope and competitor-role classification rules.

This module is also bundled into the standalone notebook.
"""

import re
import tldextract

# SERVICE-ONLY-IMPORTS: start
from .domains import get_root_domain
from .primitives import normalize_confidence
# SERVICE-ONLY-IMPORTS: end


LOCKED_SCOPE_VALIDATION_LIMIT = 12

LOCKED_SCOPE_VALIDATION_WORKERS = 5

LOCKED_SCOPE_MIN_CONFIDENCE = 0.5

LOCKED_SCOPE_CLASSIFICATION_MIN_CONFIDENCE = 0.6

LOCKED_SCOPE_CONFLICT_RETRY_MAX_RANK = 5

LOCKED_SCOPE_CONFLICT_RETRY_MIN_CONFIDENCE = 0.8


LOCKED_SCOPE_ROLE_ALIASES = {
    "marketplace": {
        "marketplace",
        "classifieds marketplace",
        "classified marketplace",
        "classifieds platform",
        "listing marketplace",
        "listing platform",
        "two sided marketplace",
        "two-sided marketplace",
        "matching platform",
        "online automotive marketplace",
        "automotive marketplace",
    },
    "aggregator_or_comparison": {
        "aggregator",
        "meta search",
        "metasearch",
        "search engine",
        "comparison engine",
        "price comparison",
        "listing aggregator",
        "aggregates listings",
        "collects listings",
        "collects advertisements",
        "collects ads",
    },
    "retailer_or_dealer": {
        "retailer",
        "dealer",
        "dealership",
        "online dealer",
        "online dealership",
        "used car dealer",
        "direct seller",
        "inventory owner",
        "inventory owning seller",
        "inventory-owning seller",
        "sells its own inventory",
        "owns the vehicles",
        "ecommerce retailer",
        "e-commerce retailer",
    },
    "manufacturer": {
        "manufacturer",
        "product manufacturer",
        "device manufacturer",
        "equipment manufacturer",
        "product brand",
    },
    "software_vendor": {
        "software vendor",
        "saas vendor",
        "software platform",
        "technology vendor",
    },
    "service_provider": {
        "service provider",
        "professional service",
        "professional practice",
        "agency",
        "consultancy",
    },
    "publisher_or_directory": {
        "publisher",
        "editorial",
        "media",
        "directory",
        "review site",
        "comparison site",
        "community",
        "forum",
    },
    "supplier_or_downstream": {
        "supplier",
        "distributor",
        "reseller",
        "customer",
        "downstream provider",
        "implementation partner",
    },
}


LOCKED_SCOPE_KNOWN_ROLES = {
    "marketplace",
    "aggregator_or_comparison",
    "retailer_or_dealer",
    "manufacturer",
    "software_vendor",
    "service_provider",
    "publisher_or_directory",
    "supplier_or_downstream",
    "government",
    "educational_resource",
    "unrelated",
    "other",
}


LOCKED_SCOPE_REJECTED_ROLES = {
    "aggregator_or_comparison",
    "publisher_or_directory",
    "supplier_or_downstream",
    "government",
    "educational_resource",
    "unrelated",
}


LOCKED_SCOPE_INACTIVE_TERMS = {
    "discontinued",
    "shut down",
    "shutting down",
    "ceased operations",
    "no longer operating",
    "no longer available",
    "service ended",
    "service has ended",
    "closed permanently",
}


LOCKED_SCOPE_COUNTRY_TLDS = {
    "DE": "de",
    "AT": "at",
    "CH": "ch",
    "FR": "fr",
    "IT": "it",
    "ES": "es",
    "NL": "nl",
    "BE": "be",
    "PL": "pl",
    "PT": "pt",
    "SE": "se",
    "NO": "no",
    "DK": "dk",
    "FI": "fi",
    "GB": "uk",
    "UK": "uk",
    "IE": "ie",
    "US": "com",
    "CA": "ca",
    "AU": "com.au",
    "JP": "jp",
    "BR": "com.br",
    "MX": "com.mx",
}


def locked_scope_brand_family(domain):
    """Collapse subdomains to a registrable brand-family label."""
    domain = get_root_domain(domain)
    if not domain:
        return ""
    extracted = tldextract.extract(domain)
    return str(extracted.domain or "").strip().lower() or domain


def locked_scope_local_domain_bonus(domain, country_code):
    """Prefer domains ending in the target market's configured country TLD."""
    domain = get_root_domain(domain)
    country_code = str(country_code or "").upper()
    country_tld = LOCKED_SCOPE_COUNTRY_TLDS.get(country_code)
    if not country_tld:
        return 0
    return 20 if domain.endswith("." + country_tld) else 0


def locked_scope_normalize_text(
    value,
):
    return re.sub(
        r"\s+",
        " ",
        str(value or "")
        .strip()
        .lower()
        .replace("-", " "),
    )


def locked_scope_role(
    value,
):
    normalized = (
        locked_scope_normalize_text(
            value
        )
    )

    normalized_key = (
        normalized.replace(
            " ",
            "_",
        )
    )

    if normalized_key in LOCKED_SCOPE_KNOWN_ROLES:
        return normalized_key

    for role_name, aliases in (
        LOCKED_SCOPE_ROLE_ALIASES.items()
    ):
        if any(
            alias in normalized
            for alias in aliases
        ):
            return role_name

    return (
        normalized_key
        or "other"
    )


def infer_locked_target_role(
    brand,
    category,
    audit_focus="",
):
    text = locked_scope_normalize_text(
        " ".join(
            [
                str(category or ""),
                str(audit_focus or ""),
                str(
                    brand.description
                    or ""
                ),
                str(
                    brand.positioning
                    or ""
                ),
                " ".join(
                    brand.products or []
                ),
            ]
        )
    )

    role_order = (
        (
            "marketplace",
            (
                "marketplace",
                "classified",
                "listing platform",
                "matching platform",
                "two sided platform",
            ),
        ),
        (
            "aggregator_or_comparison",
            (
                "aggregator",
                "metasearch",
                "meta search",
                "comparison engine",
                "price comparison",
                "search engine collecting",
            ),
        ),
        (
            "manufacturer",
            (
                "manufacturer",
                "manufactures",
                "product brand",
                "medical device",
                "consumer electronics",
                "appliance",
                "physical product",
                "hardware product",
                "personal care device",
                "equipment maker",
                "industrial equipment",
                "automation hardware",
                "control system",
                "motion control",
                "servo drive",
                "drive system",
                "hmi panel",
                "programmable logic controller",
                "plc controller",
                "robotics controller",
                "cnc control",
            ),
        ),
        (
            "software_vendor",
            (
                "software",
                "saas",
                "technology vendor",
            ),
        ),
        (
            "retailer_or_dealer",
            (
                "retailer",
                "dealership",
                "direct seller",
                "inventory owner",
                "store",
            ),
        ),
        (
            "service_provider",
            (
                "service provider",
                "professional service",
                "consulting",
                "consultancy",
                "advisory service",
                "agency",
                "managed service",
                "professional practice",
            ),
        ),
    )

    for role_name, terms in role_order:
        if any(
            term in text
            for term in terms
        ):
            return role_name

    if (
        brand.products
        and any(
            term in text
            for term in (
                "industrial automation",
                "machine tool automation",
                "machine tools automation",
                "factory automation",
            )
        )
    ):
        return "manufacturer"

    if (
        brand.products
        and re.search(
            r"\b(products?|goods?|devices?|equipment)\b",
            text,
        )
    ):
        return "manufacturer"

    return "other"


def infer_locked_business_model(
    role,
    brand,
):
    if role == "marketplace":
        return (
            "Two-sided platform connecting "
            "independent buyers and sellers "
            "through third-party listings"
        )

    if role == "aggregator_or_comparison":
        return (
            "Aggregation or comparison layer "
            "indexing offers from other providers"
        )

    if role == "retailer_or_dealer":
        return (
            "Direct seller or inventory-owning "
            "retail operation"
        )

    if role == "manufacturer":
        return (
            "Creates and sells its own products "
            "or equipment"
        )

    if role == "software_vendor":
        return (
            "Develops and sells a software product "
            "or platform"
        )

    return (
        str(
            brand.positioning
            or brand.description
            or "Service provider"
        )
    )


def build_locked_target_scope(
    brand,
    settings,
):
    category_override = str(
        settings.get(
            "market_category_override",
            "",
        )
        or ""
    ).strip()

    locked_category = (
        category_override
        or str(
            brand.category or ""
        ).strip()
    )

    raw_classified_role = str(
        getattr(
            brand,
            "primary_market_role",
            "",
        )
        or ""
    ).strip()

    classified_role = locked_scope_role(
        raw_classified_role
    )

    classification_confidence = (
        normalize_confidence(
            getattr(
                brand,
                "classification_confidence",
                0.0,
            )
        )
    )

    classification_is_usable = (
        bool(raw_classified_role)
        and classified_role
        in LOCKED_SCOPE_KNOWN_ROLES
        and classified_role
        not in {
            "other",
            "unrelated",
        }
        and classification_confidence
        >= LOCKED_SCOPE_CLASSIFICATION_MIN_CONFIDENCE
    )

    if classification_is_usable:
        market_role = classified_role
        classification_source = "stage_1_ai"
    else:
        market_role = (
            infer_locked_target_role(
                brand,
                locked_category,
                settings.get(
                    "audit_focus",
                    "",
                ),
            )
        )
        classification_source = (
            "heuristic_fallback"
        )

    secondary_market_roles = []

    for value in getattr(
        brand,
        "secondary_market_roles",
        [],
    ) or []:
        role = locked_scope_role(value)

        if (
            role in LOCKED_SCOPE_KNOWN_ROLES
            and role not in {
                market_role,
                "other",
                "unrelated",
            }
            and role
            not in secondary_market_roles
        ):
            secondary_market_roles.append(role)

    return {
        "brand_name": (
            brand.brand_name
        ),
        "official_url": (
            brand.official_url
        ),
        "domain": brand.domain,
        "category": locked_category,
        "category_source": (
            "user_override"
            if category_override
            else "stage_1_research"
        ),
        "market_role": market_role,
        "secondary_market_roles": (
            secondary_market_roles[:4]
        ),
        "offering_type": str(
            getattr(
                brand,
                "offering_type",
                "",
            )
            or ""
        ).strip(),
        "value_chain_position": str(
            getattr(
                brand,
                "value_chain_position",
                "",
            )
            or ""
        ).strip(),
        "substitute_definition": str(
            getattr(
                brand,
                "substitute_definition",
                "",
            )
            or ""
        ).strip(),
        "classification_confidence": (
            classification_confidence
        ),
        "classification_evidence": list(
            getattr(
                brand,
                "classification_evidence",
                [],
            )[:6]
        ),
        "classification_source": (
            classification_source
        ),
        "business_model": (
            infer_locked_business_model(
                market_role,
                brand,
            )
        ),
        "primary_customers": list(
            brand.target_customers[:6]
        ),
        "core_offerings": list(
            brand.products[:6]
        ),
        "country": str(
            settings.get(
                "country",
                "",
            )
            or ""
        ).upper(),
        "audit_focus": str(
            settings.get(
                "audit_focus",
                "",
            )
            or ""
        ).strip(),
        "as_of_date": str(
            settings.get("audit_as_of_date", "") or ""
        ).strip(),
        "locked": True,
        "locked_at_stage": (
            "company_analysis"
        ),
    }


def restore_locked_target_scope(company_checkpoint, brand, settings):
    """Keep a resumed audit's original scope and backfill its original date."""
    saved = company_checkpoint.get("locked_target_scope")
    scope = dict(saved) if isinstance(saved, dict) and saved else (
        build_locked_target_scope(brand, settings)
    )
    if not scope.get("as_of_date"):
        scope["as_of_date"] = str(settings.get("audit_as_of_date") or "").strip()
    return scope


def rank_valid_competitors(validation_results):
    """Keep only eligible direct competitors in the audit's stable rank order."""
    valid_results = [
        result
        for result in validation_results
        if (
            result.get("status") == "success"
            and result.get("validation", {}).get("is_direct_competitor")
            and not result.get("selection_ineligible_reason")
        )
    ]
    valid_results.sort(
        key=lambda result: (
            -result.get("selection_score", 0),
            result["candidate_record"]["discovery_rank"],
            -result["candidate_record"]["market_prominence"],
            -result["candidate_record"]["observed_score"],
        )
    )
    return valid_results
