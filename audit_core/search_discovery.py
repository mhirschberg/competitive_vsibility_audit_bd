"""Measured web-search and Google AI Mode discovery orchestration.

The caller supplies provider operations and a candidate model factory. A failed
search question is unmeasured, not a zero score; Google and Bing rankings are
never mixed in one result set.
"""

import asyncio
from collections import Counter, defaultdict
from urllib.parse import urlparse

# SERVICE-ONLY-IMPORTS: start
from .domains import get_root_domain
# SERVICE-ONLY-IMPORTS: end


NON_COMPETITOR_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
    "x.com", "youtube.com", "tiktok.com", "pinterest.com", "reddit.com",
    "quora.com", "wikipedia.org", "stackoverflow.com", "stackexchange.com",
    "g2.com", "capterra.com", "trustradius.com", "trustpilot.com",
    "getapp.com", "softwareadvice.com", "sourceforge.net", "alternativeto.net",
    "saasworthy.com", "crunchbase.com", "zoominfo.com", "bloomberg.com",
    "pitchbook.com", "glassdoor.com", "indeed.com", "medium.com",
    "substack.com", "dev.to", "forbes.com", "techcrunch.com",
    "businessinsider.com", "zdnet.com", "venturebeat.com", "gartner.com",
    "forrester.com", "coursera.org", "udemy.com", "researchgate.net",
    "arxiv.org",
}


def _hostname(value):
    value = str(value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return (parsed.hostname or "").lower().removeprefix("www.")


def is_non_competitor_domain(domain):
    root = get_root_domain(domain)
    if not root:
        return True
    return any(
        root == excluded or root.endswith(f".{excluded}")
        for excluded in NON_COMPETITOR_DOMAINS
    )


def looks_like_irrelevant_result(result):
    result_url = str(result.get("url", "")).lower()
    title = str(result.get("title", "")).lower()
    return (
        any(pattern in result_url for pattern in {
            "/jobs/", "/careers/", "/job/", "/news/", "/press/",
            "/events/", "/webinar/", "/podcast/",
        })
        or any(pattern in title for pattern in {
            "salary", "jobs at", "careers at", "interview questions",
        })
    )


def preferred_homepage_url(root_domain, hostnames):
    """Prefer the most common meaningful product/company hostname."""
    host_counts = Counter(hostname for hostname in hostnames if hostname)
    preferred_hostname = (
        host_counts.most_common(1)[0][0] if host_counts else root_domain
    )
    ignored_subdomains = {
        "blog", "blogs", "docs", "documentation", "developer", "developers",
        "help", "support", "community", "forum", "forums", "news",
        "careers", "jobs",
    }
    first_label = preferred_hostname.split(".")[0].lower() if preferred_hostname else ""
    homepage_hostname = (
        preferred_hostname
        if preferred_hostname
        and preferred_hostname.endswith(root_domain)
        and first_label not in ignored_subdomains
        else root_domain
    )
    return homepage_hostname, f"https://{homepage_hostname}/"


def aggregate_competitor_domains(
    keyword_serp_results, target_domain, total_keyword_count,
    *, candidate_factory=None,
):
    """Aggregate recurring SERP domains into scored competitor candidates."""
    target_root = get_root_domain(target_domain)
    domain_data = defaultdict(lambda: {
        "ranks": [], "keywords": set(), "urls": [], "titles": [],
        "hostnames": [],
    })
    for keyword_result in keyword_serp_results:
        if not keyword_result.get("success"):
            continue
        keyword = keyword_result["keyword"]
        seen_for_keyword = set()
        for position, result in enumerate(keyword_result.get("results", []), 1):
            hostname = _hostname(result.get("url", "")) or result.get("domain", "")
            root = get_root_domain(hostname)
            if (
                not root or root == target_root or root in seen_for_keyword
                or is_non_competitor_domain(root)
                or looks_like_irrelevant_result(result)
            ):
                continue
            seen_for_keyword.add(root)
            try:
                rank = int(result.get("rank", position))
            except Exception:
                rank = position
            domain_data[root]["ranks"].append(rank)
            domain_data[root]["keywords"].add(keyword)
            domain_data[root]["urls"].append(result.get("url", ""))
            domain_data[root]["titles"].append(result.get("title", ""))
            domain_data[root]["hostnames"].append(hostname)

    factory = candidate_factory or globals().get("CompetitorCandidate")
    candidates = []
    for domain, data in domain_data.items():
        ranks = data["ranks"]
        if not ranks:
            continue
        frequency = len(data["keywords"])
        rank_score = sum(1 / max(rank, 1) for rank in ranks)
        preferred_hostname, homepage = preferred_homepage_url(
            domain, data["hostnames"],
        )
        total_score = (
            frequency * 100 + rank_score * 25 + max(0, 11 - min(ranks))
        )
        candidate = {
            "domain": domain,
            "preferred_hostname": preferred_hostname,
            "homepage_url": homepage,
            "frequency": frequency,
            "keyword_coverage": round(frequency / total_keyword_count, 4),
            "best_rank": min(ranks),
            "average_rank": round(sum(ranks) / len(ranks), 2),
            "rank_score": round(rank_score, 4),
            "total_score": round(total_score, 2),
            "matched_keywords": sorted(data["keywords"]),
            "serp_urls": [url for url in data["urls"] if url],
            "serp_titles": [title for title in data["titles"] if title],
        }
        candidates.append(factory(**candidate) if factory else candidate)
    candidates.sort(key=lambda item: (
        -item.frequency, -item.total_score, item.average_rank, item.domain,
    ))
    return candidates


def build_ai_mode_source_candidates(
    question_results, target_domain, *, candidate_factory=None,
):
    """Turn recurring AI Mode citation domains into candidate records."""
    target_root = get_root_domain(target_domain)
    excluded = {
        target_root, "google.com", "youtube.com", "facebook.com", "instagram.com",
        "linkedin.com", "twitter.com", "x.com", "tiktok.com", "pinterest.com",
        "wikipedia.org",
    }
    source_data = defaultdict(lambda: {
        "questions": set(), "positions": [], "urls": [], "titles": [],
    })
    for result in question_results:
        if not result.get("success"):
            continue
        question = result["question"]
        seen_for_question = set()
        for citation in result.get("citations", []):
            domain = citation["domain"]
            if not domain or domain in excluded or domain in seen_for_question:
                continue
            seen_for_question.add(domain)
            source_data[domain]["questions"].add(question)
            source_data[domain]["positions"].append(citation["position"])
            source_data[domain]["urls"].append(citation["url"])
            source_data[domain]["titles"].append(citation["title"])

    factory = candidate_factory or globals().get("CompetitorCandidate")
    total_questions = max(1, len(question_results))
    candidates = []
    for domain, data in source_data.items():
        positions = data["positions"]
        frequency = len(data["questions"])
        preferred_url = data["urls"][0] if data["urls"] else f"https://{domain}/"
        preferred_hostname = _hostname(preferred_url) or domain
        rank_score = sum(1 / max(position, 1) for position in positions)
        candidate = {
            "domain": domain,
            "preferred_hostname": preferred_hostname,
            "homepage_url": f"https://{preferred_hostname}/",
            "frequency": frequency,
            "keyword_coverage": round(frequency / total_questions, 4),
            "best_rank": min(positions),
            "average_rank": round(sum(positions) / len(positions), 2),
            "rank_score": round(rank_score, 4),
            "total_score": round(frequency * 80 + rank_score * 20, 2),
            "matched_keywords": sorted(data["questions"]),
            "serp_urls": list(dict.fromkeys(data["urls"])),
            "serp_titles": list(dict.fromkeys(data["titles"])),
        }
        candidates.append(factory(**candidate) if factory else candidate)
    candidates.sort(key=lambda item: (
        -item.frequency, -item.total_score, item.average_rank, item.domain,
    ))
    return candidates


def merge_discovery_candidates(serp_candidates, ai_mode_candidates):
    """Merge candidates without equating SERP and citation rank scales."""
    merged = {candidate.domain: candidate for candidate in serp_candidates}
    for ai_candidate in ai_mode_candidates:
        existing = merged.get(ai_candidate.domain)
        if existing is None:
            merged[ai_candidate.domain] = ai_candidate
            continue
        existing.total_score = round(
            existing.total_score + ai_candidate.frequency * 40
            + ai_candidate.rank_score * 10,
            2,
        )
        existing.matched_keywords = list(dict.fromkeys([
            *existing.matched_keywords,
            *["AI Mode: " + item for item in ai_candidate.matched_keywords],
        ]))
        existing.serp_urls = list(dict.fromkeys([
            *existing.serp_urls, *ai_candidate.serp_urls,
        ]))
        existing.serp_titles = list(dict.fromkeys([
            *existing.serp_titles, *ai_candidate.serp_titles,
        ]))
    candidates = list(merged.values())
    candidates.sort(key=lambda item: (
        -item.total_score, -item.frequency, item.average_rank, item.domain,
    ))
    return candidates


async def run_search_discovery_core(
    keywords, target_domain, *, client, requested_engine,
    measure_google_ai_mode, wait_longer_for_google_ai_mode,
    only_reuse_google_ai, run_ai_mode_question, run_keyword_serp_task,
    model_to_dict, candidate_factory=None,
):
    requested_engine = str(requested_engine or "auto").strip().lower()
    active_engine = await asyncio.to_thread(
        client.choose_search_engine, keywords[0], requested_engine,
    )
    question_inputs = list(keywords[:3])

    async def run_ai_mode_batch():
        # One inexpensive health check precedes the two remaining questions.
        first = await run_ai_mode_question(
            question=question_inputs[0], question_index=1,
            timeout_seconds=(
                1800 if wait_longer_for_google_ai_mode
                else 720 if only_reuse_google_ai else 120
            ),
            max_attempts=1,
        )
        if not first.get("success"):
            client.log(
                "Google AI Mode is unavailable; skipping its remaining "
                "buyer questions. ChatGPT/Gemini will still be measured.",
                "yellow",
            )
            return [first] + [
                {
                    "question_index": index, "question": question,
                    "success": False, "answer": "", "citations": [],
                    "error": "Skipped after Google AI Mode health check.",
                }
                for index, question in enumerate(question_inputs[1:], 2)
            ]
        rest = await asyncio.gather(*(
            run_ai_mode_question(
                question=question, question_index=index,
                timeout_seconds=1800 if wait_longer_for_google_ai_mode else 720,
            )
            for index, question in enumerate(question_inputs[1:], 2)
        ))
        return [first, *rest]

    if active_engine:
        semaphore = asyncio.Semaphore(min(4, len(keywords)))
        search_tasks = [
            lambda keyword=keyword: run_keyword_serp_task(
                keyword=keyword, semaphore=semaphore, num_results=20,
                search_engine=active_engine,
            )
            for keyword in keywords
        ]

        async def run_search_batch():
            # One failed query must not discard the remaining measurements.
            first = await asyncio.gather(*(task() for task in search_tasks[:4]))
            if not any(item.get("success") for item in first):
                return first
            rest = await asyncio.gather(*(task() for task in search_tasks[4:]))
            return [*first, *rest]

        search_results, ai_mode_results = await asyncio.gather(
            run_search_batch(),
            run_ai_mode_batch() if measure_google_ai_mode
            else asyncio.sleep(0, result=[]),
        )
    else:
        search_results = []
        ai_mode_results = (
            await run_ai_mode_batch() if measure_google_ai_mode else []
        )

    if (
        active_engine == "google" and requested_engine == "auto"
        and sum(bool(result.get("success")) for result in search_results)
        < max(1, len(keywords) - 1)
    ):
        client.log(
            "Google search coverage is low. Trying the whole "
            "keyword set on Bing; rankings will not be mixed.",
            "yellow",
        )
        google_results = search_results
        bing_semaphore = asyncio.Semaphore(4)
        bing_probe = await run_keyword_serp_task(
            keyword=keywords[0], semaphore=bing_semaphore,
            num_results=20, search_engine="bing",
        )
        if bing_probe.get("success"):
            bing_rest = await asyncio.gather(*(
                run_keyword_serp_task(
                    keyword=keyword, semaphore=bing_semaphore,
                    num_results=20, search_engine="bing",
                )
                for keyword in keywords[1:]
            ))
            bing_results = [bing_probe, *bing_rest]
            if sum(bool(item.get("success")) for item in bing_results) > sum(
                bool(item.get("success")) for item in google_results
            ):
                search_results = bing_results
                active_engine = "bing"
                client.active_search_engine = "bing"
        else:
            search_results = google_results

    measured_searches = sum(bool(item.get("success")) for item in search_results)
    if active_engine and not measured_searches:
        active_engine = None
        search_status = "unavailable"
        client.active_search_engine = None
    elif active_engine and measured_searches < len(keywords):
        search_status = "partial"
        client.log(
            f"Traditional search measured {measured_searches}/{len(keywords)} "
            f"buyer questions on {active_engine.title()}; unmeasured "
            "questions are excluded from visibility denominators.",
            "yellow",
        )
    elif active_engine:
        search_status = "available"
    else:
        search_status = "unavailable"

    successful_searches = [
        item for item in search_results if item.get("success")
    ]
    successful_ai_mode = [
        item for item in ai_mode_results if item.get("success")
    ]
    if client.debug:
        for result in successful_searches:
            domains = []
            for item in result.get("results", []):
                domain = item.get("domain")
                if domain and domain not in domains:
                    domains.append(domain)
            client.log(
                f"{active_engine.title()} SERP {result['keyword']!r}: "
                f"{len(result['results'])} organic results; "
                f"domains={', '.join(domains[:8])}"
            )
        for result in ai_mode_results:
            if result.get("success"):
                client.log(
                    f"AI Mode question {result['question_index']}: "
                    f"{len(result['citations'])} citations; "
                    f"{len(result['answer'])} answer characters"
                )

    search_candidates = (
        aggregate_competitor_domains(
            keyword_serp_results=search_results,
            target_domain=target_domain,
            total_keyword_count=len(keywords),
            candidate_factory=candidate_factory,
        ) if search_results else []
    )
    ai_mode_candidates = build_ai_mode_source_candidates(
        question_results=ai_mode_results, target_domain=target_domain,
        candidate_factory=candidate_factory,
    )
    merged_candidates = merge_discovery_candidates(
        serp_candidates=search_candidates,
        ai_mode_candidates=ai_mode_candidates,
    )
    ai_mode_discovery = {
        "questions": question_inputs,
        "results": ai_mode_results,
        "successful": len(successful_ai_mode),
        "failed": len(ai_mode_results) - len(successful_ai_mode),
        "source_candidates": [model_to_dict(item) for item in ai_mode_candidates],
    }
    return {
        "search_engine": active_engine,
        "search_status": search_status,
        "keyword_results": search_results,
        "candidates": merged_candidates,
        "successful": len(successful_searches),
        "failed": len(keywords) - len(successful_searches),
        "ai_mode_successful": len(successful_ai_mode),
        "ai_mode_failed": len(ai_mode_results) - len(successful_ai_mode),
        "ai_mode_discovery": ai_mode_discovery,
    }
