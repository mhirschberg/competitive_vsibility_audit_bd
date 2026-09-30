"""Candidate research orchestration with provider calls supplied as a port.

``query_json(prompt)`` returns ``(raw_record, parsed_json)``. The audit core
never imports Bright Data or assumes a notebook; the caller owns the provider,
snapshot cache, parsing, logging, and persistence.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_scope_discovery(scope, observed_candidates, build_prompt, query_json):
    observed_domains = [candidate.domain for candidate in observed_candidates]
    prompt = build_prompt(scope, observed_domains)
    record, parsed = query_json(prompt)
    competitors = parsed.get("competitors", [])
    if not isinstance(competitors, list):
        competitors = []
    return {
        "record": record,
        "prompt": prompt,
        "competitors": [item for item in competitors if isinstance(item, dict)],
    }


def score_scope_candidate(candidate_record, validation, scope, local_domain_bonus):
    discovery_rank = candidate_record["discovery_rank"]
    discovery_score = (
        max(0, 1100 - (max(discovery_rank, 1) - 1) * 80)
        if discovery_rank < 999 else 0
    )
    prominence_score = max(
        candidate_record["market_prominence"], validation["market_prominence"]
    ) * 300
    confidence_score = validation["confidence"] * 200
    # Observed visibility cannot outweigh directness or market prominence.
    evidence_score = min(candidate_record["observed_score"], 125)
    local_domain_score = local_domain_bonus(
        validation["candidate_domain"], scope["country"]
    )
    return round(
        discovery_score + prominence_score + confidence_score
        + evidence_score + local_domain_score,
        2,
    )


def run_scope_validation(
    candidate_record,
    scope,
    build_prompt,
    build_retry_prompt,
    normalize_validation,
    supports_retry,
    query_json,
    local_domain_bonus,
):
    started_at = time.monotonic()
    # Keep prompt construction outside the catch, matching the old batch
    # contract: a broken prompt is a failed candidate, not a partial answer.
    prompt = build_prompt(scope, candidate_record)
    try:
        record, parsed = query_json(prompt)
        validation = normalize_validation(parsed, candidate_record, scope)
        initial_validation = None
        consistency_retry_used = False
        consistency_retry_error = None
        consistency_retry_record = None

        if not validation["is_direct_competitor"] and supports_retry(candidate_record, scope):
            consistency_retry_used = True
            initial_validation = dict(validation)
            retry_prompt = build_retry_prompt(
                scope, candidate_record, initial_validation
            )
            try:
                consistency_retry_record, retry_parsed = query_json(retry_prompt)
                validation = normalize_validation(retry_parsed, candidate_record, scope)
            except Exception as retry_exc:
                consistency_retry_error = (
                    f"{type(retry_exc).__name__}: {retry_exc}"
                )
                validation = initial_validation

        return {
            "status": "success",
            "candidate_record": candidate_record,
            "validation": validation,
            "selection_score": score_scope_candidate(
                candidate_record, validation, scope, local_domain_bonus
            ),
            "record": consistency_retry_record or record,
            "initial_record": record,
            "consistency_retry_record": consistency_retry_record,
            "consistency_retry_used": consistency_retry_used,
            "initial_validation": initial_validation,
            "consistency_retry_error": consistency_retry_error,
            "duration_seconds": round(time.monotonic() - started_at, 2),
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "candidate_record": candidate_record,
            "validation": {
                "candidate_name": candidate_record["brand_name"],
                "candidate_domain": candidate_record["representative_domain"],
                "official_url": candidate_record["official_url"],
                "candidate_role": "validation_error",
                "locked_target_role": scope["market_role"],
                "role_matches_scope": False,
                "is_direct_competitor": False,
                "reason": str(exc),
                "evidence": [],
                "confidence": 0.0,
                "market_prominence": 0.0,
            },
            "selection_score": 0.0,
            "record": None,
            "duration_seconds": round(time.monotonic() - started_at, 2),
            "error": str(exc),
        }


def run_scope_validation_batch(candidate_records, scope, validate_one, max_workers):
    if not candidate_records:
        return []
    indexed = {}
    with ThreadPoolExecutor(
        max_workers=min(max_workers, len(candidate_records))
    ) as executor:
        futures = {
            executor.submit(validate_one, candidate_record, scope): index
            for index, candidate_record in enumerate(candidate_records)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                indexed[index] = future.result()
            except Exception as exc:
                candidate_record = candidate_records[index]
                indexed[index] = {
                    "status": "failed",
                    "candidate_record": candidate_record,
                    "validation": {
                        "candidate_name": candidate_record["brand_name"],
                        "candidate_domain": candidate_record["representative_domain"],
                        "candidate_role": "validation_error",
                        "locked_target_role": scope["market_role"],
                        "role_matches_scope": False,
                        "is_direct_competitor": False,
                        "reason": str(exc),
                        "confidence": 0.0,
                    },
                    "selection_score": 0.0,
                    "record": None,
                    "error": str(exc),
                }
    return [indexed[index] for index in range(len(candidate_records))]
