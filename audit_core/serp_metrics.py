"""Measured traditional-search visibility for audited brand profiles."""

import re

# SERVICE-ONLY-IMPORTS: start
from .domains import get_root_domain
# SERVICE-ONLY-IMPORTS: end


def serp_distinctive_brand_tokens(domain, brand_name):
    root_domain = get_root_domain(domain)
    domain_label = re.sub(r"[^a-z0-9]+", "", root_domain.split(".", 1)[0].casefold())
    brand_tokens = re.findall(r"[a-z0-9]+", str(brand_name or "").casefold())
    ignored = {
        "co", "company", "corp", "corporation", "group", "inc", "labs",
        "limited", "llc", "ltd", "plc", "technologies",
    }

    if "".join(brand_tokens) == domain_label:
        return []

    return [
        token for token in brand_tokens
        if len(token) >= 3 and token not in ignored and token not in domain_label
    ]


def serp_result_matches_profile(domain, brand_name, result):
    target_root = get_root_domain(domain)
    result_root = get_root_domain(result.get("domain") or result.get("url") or "")
    if result_root != target_root:
        return False

    distinctive_tokens = serp_distinctive_brand_tokens(domain, brand_name)
    if not distinctive_tokens:
        return True

    result_tokens = set(re.findall(
        r"[a-z0-9]+",
        " ".join(
            str(result.get(field) or "")
            for field in ("url", "title", "description")
        ).casefold(),
    ))
    return any(token in result_tokens for token in distinctive_tokens)


def calculate_serp_metrics(domain, keyword_serp_results, brand_name=""):
    target_root = get_root_domain(domain)
    appearances = []

    for keyword_result in keyword_serp_results:
        if not keyword_result.get("success"):
            continue
        keyword = keyword_result["keyword"]
        for position, result in enumerate(keyword_result.get("results", []), start=1):
            if not serp_result_matches_profile(domain, brand_name, result):
                continue
            try:
                rank = int(result.get("rank", position))
            except Exception:
                rank = position
            appearances.append({
                "keyword": keyword,
                "rank": rank,
                "url": result.get("url", ""),
            })
            break

    ranks = [item["rank"] for item in appearances]
    total_keywords = sum(bool(result.get("success")) for result in keyword_serp_results)
    return {
        "domain": target_root,
        "appearances": len(appearances),
        "total_keywords": total_keywords,
        "coverage": len(appearances) / total_keywords if total_keywords else 0,
        "best_rank": min(ranks) if ranks else None,
        "average_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
        "details": appearances,
    }


def calculate_all_serp_metrics(profiles, keyword_serp_results):
    return {
        profile.domain: calculate_serp_metrics(
            profile.domain,
            keyword_serp_results,
            brand_name=profile.brand_name,
        )
        for profile in profiles
    }
