"""Conservative brand mentions in measured AI answer text."""

import re

# SERVICE-ONLY-IMPORTS: start
from .domains import get_root_domain
# SERVICE-ONLY-IMPORTS: end


def build_brand_aliases(profile):
    """Build aliases for brands, products, services, and organizations."""
    aliases = set()
    brand_name = str(profile.brand_name or "").strip()
    brand_lower = brand_name.lower()

    if brand_lower:
        aliases.add(brand_lower)
        normalized_brand = re.sub(r"[^a-z0-9]+", " ", brand_lower).strip()
        if normalized_brand and normalized_brand != brand_lower:
            aliases.add(normalized_brand)

    root_domain = get_root_domain(profile.domain)
    domain_stem = root_domain.split(".")[0] if root_domain else ""
    normalized_domain_stem = re.sub(r"[^a-z0-9]+", " ", domain_stem.lower()).strip()
    generic_terms = {
        "amazon", "azure", "google", "microsoft", "oracle", "company",
        "group", "global", "international", "product", "products",
        "service", "services", "store", "shop", "official", "online",
    }
    if len(normalized_domain_stem) >= 4 and normalized_domain_stem not in generic_terms:
        aliases.add(normalized_domain_stem)

    words = re.findall(r"[A-Za-z0-9]+", brand_name)
    normalized_words = [word.lower() for word in words]
    for index, original_word in enumerate(words):
        word = original_word.lower()
        has_internal_capital = any(character.isupper() for character in original_word[1:])
        looks_like_named_product = (
            has_internal_capital
            or (len(word) >= 6 and word.endswith("db"))
            or word == normalized_domain_stem
        )
        if word not in generic_terms and looks_like_named_product:
            aliases.add(word)
        if (index + 1 < len(normalized_words)
                and normalized_words[index + 1] == "db"
                and word not in generic_terms):
            aliases.add(f"{word} db")

    return sorted(aliases, key=len, reverse=True)


def find_brand_mentions(answer, profiles):
    answer = str(answer or "")
    results = []

    for profile in profiles:
        aliases = build_brand_aliases(profile)
        all_positions = []
        matched_aliases = []
        for alias in aliases:
            matches = list(re.finditer(
                rf"\b{re.escape(alias)}\b", answer, flags=re.IGNORECASE,
            ))
            if not matches:
                continue
            matched_aliases.append(alias)
            all_positions.extend(match.start() for match in matches)

        unique_positions = sorted(set(all_positions))
        results.append({
            "brand_name": profile.brand_name,
            "domain": profile.domain,
            "role": "competitor" if profile.direct_competitor else "target",
            "mentioned": bool(unique_positions),
            "mention_count": len(unique_positions),
            "first_position": unique_positions[0] if unique_positions else None,
            "matched_aliases": sorted(set(matched_aliases)),
        })

    results.sort(key=lambda item: (
        not item["mentioned"],
        item["first_position"] if item["first_position"] is not None else float("inf"),
    ))
    return results


def mention_order(mentions):
    return [item["brand_name"] for item in mentions if item["mentioned"]]
