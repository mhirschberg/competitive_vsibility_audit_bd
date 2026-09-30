"""Measured AI-answer orchestration shared by hosted and notebook runners.

The caller supplies the provider client, localized prompt builder, and the
already-collected Google AI Mode discovery sample. This module does not own
their storage or network configuration.
"""

import asyncio
import time

# SERVICE-ONLY-IMPORTS: start
from .brand_mentions import find_brand_mentions
# SERVICE-ONLY-IMPORTS: end


async def run_visibility_stage_core(
    target_profile,
    all_profiles,
    keywords,
    *,
    bd_client,
    prompt_builder,
    ai_mode_discovery=None,
    include_copilot=False,
    include_google_ai_mode=True,
    include_chatgpt=True,
    include_gemini=True,
    wait_longer_for_chatgpt=False,
    wait_longer_for_gemini=False,
    wait_longer_for_copilot=False,
):
    """Measure real provider answers; unavailable answers remain unknown."""
    prompt = prompt_builder(target_profile=target_profile, keywords=keywords)

    async def run_engine(engine, redundancy=3, timeout_seconds=600):
        started_at = time.monotonic()
        try:
            result = await asyncio.to_thread(
                bd_client.race_ai_engine, engine, prompt, redundancy, timeout_seconds,
            )
            result["duration_seconds"] = round(time.monotonic() - started_at, 2)
            return result
        except Exception as exc:
            return {
                "engine": engine,
                "engine_name": {
                    "chatgpt": "ChatGPT", "gemini": "Gemini", "copilot": "Copilot",
                }[engine],
                "status": "failed",
                "answer": "",
                "citations": [],
                "web_search_triggered": None,
                "duration_seconds": round(time.monotonic() - started_at, 2),
                "error": str(exc),
            }

    scheduled = []
    if include_chatgpt:
        scheduled.append(("chatgpt", run_engine(
            "chatgpt", timeout_seconds=1800 if wait_longer_for_chatgpt else 600,
        )))
    if include_gemini:
        scheduled.append(("gemini", run_engine(
            "gemini", timeout_seconds=1800 if wait_longer_for_gemini else 600,
        )))
    if include_copilot:
        # A single Copilot snapshot is an optional measurement, not a race.
        scheduled.append(("copilot", run_engine(
            "copilot", redundancy=1,
            timeout_seconds=900 if wait_longer_for_copilot else 360,
        )))

    completed = await asyncio.gather(*(task for _, task in scheduled))
    engine_results = {
        engine: result for (engine, _), result in zip(scheduled, completed)
    }

    ai_mode_discovery = ai_mode_discovery or {
        "results": [], "successful": 0, "failed": 0,
    }
    successful_ai_answers = [
        result for result in ai_mode_discovery.get("results", [])
        if result.get("success") and result.get("answer")
    ]
    ai_mode_answers = [result["answer"] for result in successful_ai_answers]
    ai_mode_citations = []
    for result in successful_ai_answers:
        ai_mode_citations.extend(result.get("citations", []))

    google_ai_result = {
        "engine": "google_ai_mode",
        "engine_name": "Google AI Mode",
        "status": (
            "success" if len(successful_ai_answers) == 3
            else "partial" if ai_mode_answers else "unavailable"
        ),
        "answer": "\n\n".join(ai_mode_answers),
        "citations": ai_mode_citations,
        "web_search_triggered": None,
        "error": (
            (ai_mode_discovery.get("results") or [{}])[0].get("error")
            if not successful_ai_answers else None
        ),
        "question_count": len(ai_mode_discovery.get("results", [])),
        "successful_questions": len(successful_ai_answers),
        "failed_questions": (
            len(ai_mode_discovery.get("results", [])) - len(successful_ai_answers)
        ),
    }
    if include_google_ai_mode:
        engine_results = {"google_ai_mode": google_ai_result, **engine_results}

    mentions = {}
    combined_google_mentions = (
        find_brand_mentions(google_ai_result.get("answer", ""), all_profiles)
        if google_ai_result["status"] == "success" else []
    )
    google_mentions_by_domain = {
        item["domain"]: item for item in combined_google_mentions
    }
    google_coverage_total = len(
        successful_ai_answers if google_ai_result["status"] == "success" else []
    )

    for profile in all_profiles:
        domain = profile.domain
        mention = google_mentions_by_domain.get(domain, {
            "brand_name": profile.brand_name,
            "domain": domain,
            "role": "competitor" if profile.direct_competitor else "target",
            "mentioned": False,
            "mention_count": 0,
            "first_position": None,
            "matched_aliases": [],
        })
        answer_appearances = 0
        for question_result in (
            successful_ai_answers if google_ai_result["status"] == "success" else []
        ):
            question_mentions = find_brand_mentions(question_result["answer"], [profile])
            if question_mentions and question_mentions[0]["mentioned"]:
                answer_appearances += 1
        mention["answer_appearances"] = answer_appearances
        mention["answer_total"] = google_coverage_total
        mention["answer_coverage"] = (
            answer_appearances / google_coverage_total if google_coverage_total else 0
        )
        google_mentions_by_domain[domain] = mention

    mentions["google_ai_mode"] = sorted(
        google_mentions_by_domain.values(),
        key=lambda item: (
            not item["mentioned"],
            item["first_position"] if item["first_position"] is not None else float("inf"),
        ),
    )
    if not include_google_ai_mode or google_ai_result["status"] != "success":
        # An unavailable sample is unknown, not three measured absences.
        mentions["google_ai_mode"] = []

    for engine in (
        item for item in ("chatgpt", "gemini", "copilot") if item in engine_results
    ):
        result = engine_results[engine]
        if result.get("status") != "success":
            mentions[engine] = []
            continue
        engine_mentions = find_brand_mentions(result.get("answer", ""), all_profiles)
        for mention in engine_mentions:
            mention["answer_appearances"] = 1 if mention["mentioned"] else 0
            mention["answer_total"] = 1
            mention["answer_coverage"] = 1.0 if mention["mentioned"] else 0.0
        mentions[engine] = engine_mentions

    audited_domains = {
        profile.domain: profile.brand_name for profile in all_profiles
    }
    return {
        "prompt": prompt,
        "engines": engine_results,
        "mentions": mentions,
        "ai_mode_discovery": ai_mode_discovery,
        "audited_domains": audited_domains,
    }
