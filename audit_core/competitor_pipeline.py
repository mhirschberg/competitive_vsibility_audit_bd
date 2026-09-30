"""Notebook-independent adapter for locked-scope competitor research.

The caller owns the AI client, snapshot cache, and environment-specific URL
helpers. This module wires them to the shared discovery and validation code.
"""

from pathlib import Path

# SERVICE-ONLY-IMPORTS: start
from .competitor_decisions import (
    core_build_locked_candidate_universe,
    core_build_locked_scope_discovery_prompt,
    core_build_locked_scope_validation_prompt,
    core_build_locked_scope_validation_retry_prompt,
    core_discovery_supports_consistency_retry,
    core_normalize_locked_scope_validation,
)
from .competitor_research import (
    run_scope_discovery,
    run_scope_validation,
    run_scope_validation_batch,
)
# SERVICE-ONLY-IMPORTS: end


def query_google_ai_json(client, parse_ai_json, prompt, timeout_seconds=720):
    """Return both the original provider record and its parsed answer."""
    record = client.google_ai_mode(prompt, timeout_seconds=timeout_seconds)
    return record, parse_ai_json(client.answer_text(record))


def persist_validation_checkpoint(output_dir, write_json, payload):
    """Save raw candidate evidence only when an audit directory is active."""
    if output_dir is not None:
        write_json(
            Path(output_dir) / "raw" / "03_candidate_validation_records.json",
            payload,
        )


def serialize_scope_validation(result):
    """Keep the same checkpoint shape for service and generated notebook."""
    candidate = result["candidate_record"]
    return {
        "status": result.get("status"),
        "candidate": {
            "brand_name": candidate["brand_name"],
            "domain": candidate["representative_domain"],
            "domains": candidate["domains"],
            "discovery_rank": candidate["discovery_rank"],
            "observed_score": candidate["observed_score"],
            "observed_frequency": candidate["observed_frequency"],
        },
        "validation": result.get("validation"),
        "selection_ineligible_reason": result.get("selection_ineligible_reason"),
        "consistency_retry_used": result.get("consistency_retry_used", False),
        "initial_validation": result.get("initial_validation"),
        "consistency_retry_error": result.get("consistency_retry_error"),
        "selection_score": result.get("selection_score"),
        "duration_seconds": result.get("duration_seconds"),
        "error": result.get("error"),
    }


class CompetitorPipeline:
    """Wire pure decisions, provider queries, and bounded candidate work."""

    def __init__(self, *, query_json, decision_ports, local_domain_bonus,
                 validation_workers):
        self.query_json = query_json
        self.decision_ports = decision_ports
        self.local_domain_bonus = local_domain_bonus
        self.validation_workers = validation_workers

    def discovery_prompt(self, scope, observed_domains):
        return core_build_locked_scope_discovery_prompt(
            scope, observed_domains, self.decision_ports
        )

    def discover(self, scope, observed_candidates):
        return run_scope_discovery(
            scope, observed_candidates, self.discovery_prompt, self.query_json
        )

    def build_universe(self, *, observed_candidates, discovered_candidates, scope):
        return core_build_locked_candidate_universe(
            observed_candidates, discovered_candidates, scope,
            self.decision_ports,
        )

    def validation_prompt(self, scope, candidate_record):
        return core_build_locked_scope_validation_prompt(
            scope, candidate_record, self.decision_ports
        )

    @staticmethod
    def retry_prompt(scope, candidate_record, initial_validation):
        return core_build_locked_scope_validation_retry_prompt(
            scope, candidate_record, initial_validation
        )

    def normalize(self, data, candidate_record, scope):
        return core_normalize_locked_scope_validation(
            data, candidate_record, scope, self.decision_ports
        )

    @staticmethod
    def supports_retry(candidate_record, scope, max_rank=None):
        if max_rank is None:
            return core_discovery_supports_consistency_retry(
                candidate_record, scope
            )
        return core_discovery_supports_consistency_retry(
            candidate_record, scope, max_rank=max_rank
        )

    def validate_candidate(self, candidate_record, scope):
        return run_scope_validation(
            candidate_record, scope, self.validation_prompt,
            self.retry_prompt, self.normalize, self.supports_retry,
            self.query_json, self.local_domain_bonus,
        )

    def validate_batch(self, candidate_records, scope):
        return run_scope_validation_batch(
            candidate_records, scope, self.validate_candidate,
            self.validation_workers,
        )

    def mark_uncorroborated(self, validation_candidates, validation_results,
                            scope):
        """Prevent search-only domains from displacing discovery-backed peers."""
        corroborated = [
            item for item in validation_candidates
            if self.supports_retry(item, scope, max_rank=998)
        ]
        if len(corroborated) < 2:
            return
        for result in validation_results:
            if not self.supports_retry(
                result["candidate_record"], scope, max_rank=998
            ):
                result["selection_ineligible_reason"] = (
                    "Only observed in search; not corroborated by the "
                    "locked-scope competitor discovery."
                )
