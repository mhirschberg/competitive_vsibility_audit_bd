"""Build target and competitor profiles through explicit provider ports."""

import asyncio


class ProfileResearchPorts:
    def __init__(
        self, *, generate_profile, recover_profile, fallback_profile,
        root_domain, pending_notice,
    ):
        self.generate_profile = generate_profile
        self.recover_profile = recover_profile
        self.fallback_profile = fallback_profile
        self.root_domain = root_domain
        self.pending_notice = pending_notice


async def run_profile_research_core(
    target_brand, selected_competitors, audit_focus="", *, ports,
):
    jobs = [{
        "role": "target",
        "brand_name": target_brand.brand_name,
        "official_url": target_brand.official_url,
        "domain": target_brand.domain,
        "reason": "",
    }]
    jobs.extend({
        "role": "competitor",
        "brand_name": competitor.brand_name,
        "official_url": competitor.official_url,
        "domain": competitor.domain,
        "reason": competitor.reason,
    } for competitor in selected_competitors)

    results = await asyncio.gather(*(
        asyncio.to_thread(
            ports.generate_profile, job, target_brand, audit_focus,
        ) for job in jobs
    ))
    pending = [result for result in results if result["status"] == "pending"]
    if pending:
        ports.pending_notice(len(pending))
        recovered = await asyncio.gather(*(
            asyncio.to_thread(ports.recover_profile, result)
            for result in pending
        ))
        recovered_by_domain = {
            item["job"]["domain"]: item for item in recovered
        }
        results = [
            recovered_by_domain.get(item["job"]["domain"], item)
            if item["status"] == "pending" else item
            for item in results
        ]

    profiles = []
    for result in results:
        profile = result.get("profile")
        if profile is None:
            profile = ports.fallback_profile(result["job"], target_brand)
            result["profile"] = profile
            result["used_fallback"] = True
        else:
            result["used_fallback"] = False
        profiles.append(profile)

    deduplicated = []
    seen = set()
    for profile in profiles:
        key = (profile.direct_competitor, ports.root_domain(profile.domain))
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(profile)
    target_profile = next(
        (profile for profile in deduplicated if not profile.direct_competitor),
        ports.fallback_profile(jobs[0], target_brand),
    )
    competitor_profiles = [
        profile for profile in deduplicated if profile.direct_competitor
    ]
    return {
        "target_profile": target_profile,
        "competitor_profiles": competitor_profiles,
        "all_profiles": [target_profile, *competitor_profiles],
        "task_results": results,
        "successful": sum(result["status"] == "success" for result in results),
        "fallbacks": sum(result.get("used_fallback", False) for result in results),
    }
