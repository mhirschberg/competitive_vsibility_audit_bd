"""Run competitor-selection decisions without notebook or provider globals.

The caller supplies provider operations, checkpoint persistence, and the
selected-competitor model through ``CompetitorStagePorts``. Provider adapters
still live in the notebook until the full audit runner is migrated.
"""

import json

# SERVICE-ONLY-IMPORTS: start
from .competitor_scope import rank_valid_competitors
# SERVICE-ONLY-IMPORTS: end


class CompetitorStagePorts:
    """Explicit boundary between selection decisions and external effects."""

    def __init__(
        self, *, discover, build_universe, validate_batch,
        mark_uncorroborated, brand_family, serialize_validation,
        selected_factory, error_type, validation_limit,
        only_reuse=False, cached_snapshot_ids=None, validation_prompt=None,
        persist_validation_records=None, clean_record=None,
    ):
        self.discover = discover
        self.build_universe = build_universe
        self.validate_batch = validate_batch
        self.mark_uncorroborated = mark_uncorroborated
        self.brand_family = brand_family
        self.serialize_validation = serialize_validation
        self.selected_factory = selected_factory
        self.error_type = error_type
        self.validation_limit = validation_limit
        self.only_reuse = only_reuse
        self.cached_snapshot_ids = cached_snapshot_ids
        self.validation_prompt = validation_prompt
        self.persist_validation_records = persist_validation_records
        self.clean_record = clean_record or (lambda value: value)


def _rejection_summary(results):
    return [
        {
            "brand_name": result["candidate_record"]["brand_name"],
            "domain": result["candidate_record"]["representative_domain"],
            "candidate_role": result.get("validation", {}).get("candidate_role"),
            "status": result.get("status"),
            "failed_checks": result.get("validation", {}).get("failed_checks", []),
            "validation_confidence": result.get("validation", {}).get(
                "validation_confidence", 0.0
            ),
            "discovery_confidence": result.get("validation", {}).get(
                "discovery_confidence", 0.0
            ),
            "reason": (
                result.get("selection_ineligible_reason")
                or result.get("validation", {}).get("reason")
                or result.get("error")
            ),
        }
        for result in results
    ]


def _persist_validation_records(ports, scope, discovery, results):
    if ports.persist_validation_records is None:
        return
    ports.persist_validation_records({
        "locked_scope": scope,
        "discovery": ports.clean_record(discovery["record"]),
        "candidates": [
            {
                "candidate": result["candidate_record"]["brand_name"],
                "status": result.get("status"),
                "selection_ineligible_reason": result.get("selection_ineligible_reason"),
                "validation": result.get("validation"),
                "initial_record": ports.clean_record(result.get("initial_record")),
                "retry_record": ports.clean_record(result.get("consistency_retry_record")),
                "error": result.get("error"),
            }
            for result in results
        ],
    })


def select_competitors_core(scope, candidates, keywords, ports):
    """Select two direct competitors from one locked scope and provider results."""
    discovery = ports.discover(scope, candidates)
    candidate_universe = ports.build_universe(
        observed_candidates=candidates,
        discovered_candidates=discovery["competitors"],
        scope=scope,
    )
    validation_candidates = candidate_universe[:ports.validation_limit]

    unvalidated_on_resume = 0
    if ports.only_reuse:
        previous_count = len(validation_candidates)
        validation_candidates = [
            item for item in validation_candidates
            if ports.cached_snapshot_ids(ports.validation_prompt(scope, item))
        ]
        unvalidated_on_resume = previous_count - len(validation_candidates)
        if not validation_candidates:
            raise ports.error_type(
                "No saved candidate-validation snapshots match "
                "this audit; continuation will not launch new ones."
            )

    validation_results = ports.validate_batch(validation_candidates, scope)
    ports.mark_uncorroborated(validation_candidates, validation_results, scope)
    _persist_validation_records(ports, scope, discovery, validation_results)
    valid_results = rank_valid_competitors(validation_results)

    if len(valid_results) < 2:
        rejections = _rejection_summary(validation_results)
        if validation_results and all(
            result.get("status") == "failed" for result in validation_results
        ):
            raise ports.error_type(
                "AI research providers were unavailable for every candidate. "
                "This does not mean there are no "
                "direct competitors. Continue the saved audit when "
                "the snapshots become ready. Errors: "
                + json.dumps(rejections, ensure_ascii=False)
            )
        raise ports.error_type(
            "The locked target scope produced "
            f"{len(valid_results)} valid direct "
            "competitor(s). The scope will not be "
            "broadened automatically. Rejections: "
            + json.dumps(rejections, ensure_ascii=False)
        )

    selected_results = valid_results[:2]
    selected = [
        ports.selected_factory(
            brand_name=result["validation"]["candidate_name"],
            domain=result["validation"]["candidate_domain"],
            official_url=result["validation"]["official_url"],
            reason=result["validation"]["reason"],
            confidence=result["validation"]["confidence"],
        )
        for result in selected_results
    ]
    selected_families = {ports.brand_family(item.domain) for item in selected}
    rejected = []
    for result in validation_results:
        validation = result.get("validation", {})
        family = ports.brand_family(
            validation.get("candidate_domain")
            or result["candidate_record"]["representative_domain"]
        )
        if family in selected_families:
            continue
        rejected.append({
            "brand_name": (
                validation.get("candidate_name")
                or result["candidate_record"]["brand_name"]
            ),
            "domain": (
                validation.get("candidate_domain")
                or result["candidate_record"]["representative_domain"]
            ),
            "candidate_role": validation.get("candidate_role"),
            "reason": (
                result.get("selection_ineligible_reason")
                or validation.get("reason")
                or result.get("error")
            ),
            "selection_score": result.get("selection_score"),
            "rejection_source": "locked_target_scope",
        })

    return {
        "selected": selected,
        "rejected": rejected,
        "record": discovery["record"],
        "prompt": discovery["prompt"],
        "used_fallback": False,
        "shortlist": candidates,
        "unvalidated_on_resume": unvalidated_on_resume,
        "validation_results": [
            ports.serialize_validation(result) for result in validation_results
        ],
        "top_ten_competitors": [
            {
                **result["validation"],
                "selection_score": result["selection_score"],
                "discovery_rank": result["candidate_record"]["discovery_rank"],
                "observed_score": result["candidate_record"]["observed_score"],
            }
            for result in valid_results[:10]
        ],
        "locked_target_scope": dict(scope),
        "selection_method": (
            "locked_scope_market_discovery_"
            "and_individual_validation"
        ),
    }
