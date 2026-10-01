"""Measured web-search and Google AI Mode discovery orchestration.

The caller supplies provider operations and candidate aggregation. A failed
search question is unmeasured, not a zero score; Google and Bing rankings are
never mixed in one result set.
"""

import asyncio


async def run_search_discovery_core(
    keywords, target_domain, *, client, requested_engine,
    measure_google_ai_mode, wait_longer_for_google_ai_mode,
    only_reuse_google_ai, run_ai_mode_question, run_keyword_serp_task,
    aggregate_competitor_domains, build_ai_mode_source_candidates,
    merge_discovery_candidates, model_to_dict,
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
        ) if search_results else []
    )
    ai_mode_candidates = build_ai_mode_source_candidates(
        question_results=ai_mode_results, target_domain=target_domain,
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
