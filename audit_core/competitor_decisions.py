"""Pure competitor shortlist, prompts, and strict AI-verdict normalization.

The few URL/country adapters arrive through ``CompetitorDecisionPorts``.
The notebook builder removes the service-only imports, because the same
helpers were embedded in earlier notebook cells.
"""

import json
from datetime import datetime, timezone

# SERVICE-ONLY-IMPORTS: start
from .competitor_scope import LOCKED_SCOPE_CONFLICT_RETRY_MAX_RANK, LOCKED_SCOPE_CONFLICT_RETRY_MIN_CONFIDENCE, LOCKED_SCOPE_INACTIVE_TERMS, LOCKED_SCOPE_MIN_CONFIDENCE, LOCKED_SCOPE_REJECTED_ROLES, locked_scope_normalize_text, locked_scope_role
from .primitives import ensure_string_list, normalize_boolean, normalize_confidence
# SERVICE-ONLY-IMPORTS: end


class CompetitorDecisionPorts:
    """Environment-specific helpers without provider or notebook state."""

    def __init__(self, country_details, get_root_domain, normalize_public_url,
                 brand_family, local_domain_bonus):
        self.country_details = country_details
        self.get_root_domain = get_root_domain
        self.normalize_public_url = normalize_public_url
        self.brand_family = brand_family
        self.local_domain_bonus = local_domain_bonus


def scope_as_of_date(scope):
    """Use the audit's original date, including when a saved run resumes."""
    saved = str(scope.get("as_of_date") or "").strip()
    return saved or datetime.now(timezone.utc).date().isoformat()


LOCKED_SCOPE_VALIDATION_CHECKS = (
    "active_in_target_country", "same_category",
    "same_market_role", "same_business_model",
    "same_primary_customers", "same_core_transaction",
    "offering_is_substitute",
)


def core_canonical_candidate_validation_data(data, target_role=None):
    """Reject incomplete verdicts; accept known structured provider variants."""
    if not isinstance(data, dict):
        raise ValueError("Candidate validation is not an object.")
    result = dict(data)
    nested = data.get("validation")
    nested = nested if isinstance(nested, dict) else {}
    for key in LOCKED_SCOPE_VALIDATION_CHECKS:
        value = data.get(key, nested.get(key))
        if key == "offering_is_substitute" and value is None:
            value = data.get("realistic_substitute", nested.get("realistic_substitute"))
        if type(value) is not bool:
            raise ValueError(f"Candidate validation lacks boolean {key}.")
        result[key] = value
    direct = data.get("is_direct_competitor")
    if type(direct) is not bool:
        for alias in ("direct_competitor", "valid_direct_competitor", "matches_target_scope"):
            if type(data.get(alias)) is bool:
                direct = data[alias]
                break
    if type(direct) is not bool:
        decision = str(data.get("decision") or data.get("validation_result") or "").upper()
        if decision in {"VALID_DIRECT_COMPETITOR", "ACCEPT"}:
            direct = True
        elif decision in {"REJECT", "NOT_DIRECT_COMPETITOR"}:
            direct = False
    if type(direct) is not bool:
        raise ValueError("Candidate validation lacks a direct-competitor verdict.")
    result["is_direct_competitor"] = direct
    role = str(data.get("candidate_role") or "").strip()
    if not role and target_role and result["same_market_role"] and isinstance(nested, dict) and nested:
        role = target_role
    if not role and not (nested and data.get("matches_target_scope") is True and result["same_market_role"]):
        raise ValueError("Candidate validation lacks a market role.")
    if role:
        result["candidate_role"] = role
    evidence = data.get("evidence")
    if isinstance(evidence, dict):
        result["evidence"] = [str(value) for value in evidence.values() if value]
    if not result.get("reason"):
        result["reason"] = str(data.get("rejection_reason") or nested.get("substitutability") or "")
    if result.get("confidence") is None and data.get("validation_confidence") is not None:
        result["confidence"] = data["validation_confidence"]
    return result


def core_build_locked_scope_discovery_prompt(
    scope,
    observed_domains,
    ports,
):
    locked_scope_country_details = ports.country_details
    country = (
        locked_scope_country_details(
            scope["country"]
        )
    )
    as_of_date = scope_as_of_date(scope)

    return f"""
Identify the strongest active direct competitors to this target in
{country["name"]} ({country["code"]}) as of {as_of_date}.

LOCKED TARGET SCOPE

Brand: {scope["brand_name"]}
Website: {scope["official_url"]}
Category: {scope["category"]}
Market role: {scope["market_role"]}
Business model: {scope["business_model"]}
Primary customers: {json.dumps(scope["primary_customers"], ensure_ascii=False)}
Core offerings: {json.dumps(scope["core_offerings"], ensure_ascii=False)}
Audit focus: {scope["audit_focus"] or "primary offering"}

The target scope above is authoritative and must not be rejected,
broadened, or reclassified.

OBSERVED DOMAINS

{json.dumps(observed_domains[:20], ensure_ascii=False)}

Identify companies that match the target's category, market role,
business model, primary customers, and core transaction.

ROLE-RELATIVE RULES

- A marketplace can directly compete with another marketplace.
- A manufacturer can directly compete with another manufacturer.
- A software vendor can directly compete with another software vendor.
- An aggregator or comparison engine is not the same as a marketplace.
- A dealership, retailer, or inventory-owning seller is not the same
  as a marketplace connecting independent buyers and sellers.
- Publishers, directories, review sites, suppliers, and downstream
  providers qualify only when the locked target has that exact role.
- Do not include inactive or discontinued services.
- Do not use search visibility as the definition of competition.
- Include important competitors even when they rank poorly or do not
  appear in the observed searches.

Return only JSON:

{{
  "competitors": [
    {{
      "rank_by_directness": 1,
      "brand_name": "canonical current name",
      "domain": "official domain",
      "official_url": "official URL",
      "candidate_category": "specific category",
      "candidate_role": "marketplace, aggregator_or_comparison, retailer_or_dealer, manufacturer, software_vendor, service_provider, publisher_or_directory, supplier_or_downstream, government, educational_resource, unrelated, or other",
      "candidate_business_model": "concise description",
      "active_in_target_country": true,
      "same_category": true,
      "same_market_role": true,
      "same_business_model": true,
      "same_primary_customers": true,
      "same_core_transaction": true,
      "offering_is_substitute": true,
      "market_prominence": 0.0,
      "reason": "why this is or is not a direct competitor",
      "evidence": ["specific current public evidence"],
      "confidence": 0.0
    }}
  ]
}}

Return up to fifteen candidates ordered by direct competitive relevance,
not by observed search visibility.
""".strip()


def core_build_locked_candidate_universe(
    observed_candidates,
    discovered_candidates,
    scope,
    ports,
):
    get_root_domain = ports.get_root_domain
    normalize_public_url = ports.normalize_public_url
    locked_scope_brand_family = ports.brand_family
    locked_scope_local_domain_bonus = ports.local_domain_bonus
    universe = {}

    def get_entry(
        domain,
    ):
        family = (
            locked_scope_brand_family(
                domain
            )
        )

        if not family:
            return None

        return universe.setdefault(
            family,
            {
                "family": family,
                "domains": set(),
                "observed_candidates": [],
                "discovery_records": [],
                "discovery_rank": 999,
                "market_prominence": 0.0,
                "discovery_confidence": 0.0,
            },
        )

    for candidate in observed_candidates:
        entry = get_entry(
            candidate.domain
        )

        if entry is None:
            continue

        entry["domains"].add(
            candidate.domain
        )

        entry[
            "observed_candidates"
        ].append(candidate)

    for item in discovered_candidates:
        domain = get_root_domain(
            item.get("domain")
            or item.get(
                "official_url"
            )
            or ""
        )

        if not domain:
            continue

        if domain == get_root_domain(
            scope["domain"]
        ):
            continue

        entry = get_entry(domain)

        if entry is None:
            continue

        entry["domains"].add(domain)

        entry[
            "discovery_records"
        ].append(item)

        try:
            rank = int(
                item.get(
                    "rank_by_directness",
                    999,
                )
                or 999
            )
        except Exception:
            rank = 999

        entry["discovery_rank"] = min(
            entry[
                "discovery_rank"
            ],
            rank,
        )

        entry[
            "market_prominence"
        ] = max(
            entry[
                "market_prominence"
            ],
            normalize_confidence(
                item.get(
                    "market_prominence"
                )
            ),
        )

        entry[
            "discovery_confidence"
        ] = max(
            entry[
                "discovery_confidence"
            ],
            normalize_confidence(
                item.get(
                    "confidence"
                )
            ),
        )

    country_code = scope[
        "country"
    ]

    target_family = (
        locked_scope_brand_family(
            scope["domain"]
        )
    )

    records = []

    for family, entry in (
        universe.items()
    ):
        if family == target_family:
            continue

        domains = sorted(
            entry["domains"],
            key=lambda domain: (
                -locked_scope_local_domain_bonus(
                    domain,
                    country_code,
                ),
                domain,
            ),
        )

        representative_domain = (
            domains[0]
            if domains
            else ""
        )

        observed = entry[
            "observed_candidates"
        ]

        discovery = entry[
            "discovery_records"
        ]

        representative_observed = (
            max(
                observed,
                key=lambda candidate: (
                    locked_scope_local_domain_bonus(
                        candidate.domain,
                        country_code,
                    ),
                    candidate.total_score,
                ),
            )
            if observed
            else None
        )

        representative_discovery = (
            min(
                discovery,
                key=lambda item: int(
                    item.get(
                        "rank_by_directness",
                        999,
                    )
                    or 999
                ),
            )
            if discovery
            else {}
        )

        brand_name = str(
            representative_discovery.get(
                "brand_name"
            )
            or (
                representative_observed.domain
                if representative_observed
                else representative_domain
            )
        ).strip()

        official_url = (
            normalize_public_url(
                representative_discovery.get(
                    "official_url"
                )
                or (
                    representative_observed
                    .homepage_url
                    if representative_observed
                    else (
                        f"https://"
                        f"{representative_domain}/"
                    )
                )
            )
            or (
                f"https://"
                f"{representative_domain}/"
            )
        )

        observed_score = max(
            (
                candidate.total_score
                for candidate in observed
            ),
            default=0.0,
        )

        observed_frequency = max(
            (
                candidate.frequency
                for candidate in observed
            ),
            default=0,
        )

        records.append(
            {
                **entry,
                "domains": domains,
                "representative_domain": (
                    representative_domain
                ),
                "brand_name": brand_name,
                "official_url": (
                    official_url
                ),
                "observed_score": (
                    observed_score
                ),
                "observed_frequency": (
                    observed_frequency
                ),
                "discovery_record": (
                    representative_discovery
                ),
            }
        )

    records.sort(
        key=lambda entry: (
            entry[
                "discovery_rank"
            ],
            -entry[
                "market_prominence"
            ],
            -entry[
                "discovery_confidence"
            ],
            -entry[
                "observed_score"
            ],
            -entry[
                "observed_frequency"
            ],
            entry[
                "representative_domain"
            ],
        )
    )

    return records


def core_build_locked_scope_validation_prompt(
    scope,
    candidate_record,
    ports,
):
    locked_scope_country_details = ports.country_details
    country = (
        locked_scope_country_details(
            scope["country"]
        )
    )

    discovery_record = (
        candidate_record.get(
            "discovery_record"
        )
        or {}
    )

    scope_summary = {
        "brand_name": scope.get("brand_name"),
        "category": str(scope.get("category") or "")[:160],
        "market_role": scope.get("market_role"),
        "business_model": str(scope.get("business_model") or "")[:180],
        "primary_customers": [str(item)[:80] for item in (scope.get("primary_customers") or [])[:4]],
        "core_offerings": [str(item)[:80] for item in (scope.get("core_offerings") or [])[:4]],
        "substitute_definition": str(scope.get("substitute_definition") or "")[:240],
        "audit_focus": str(scope.get("audit_focus") or "")[:120],
        "country": scope.get("country"),
    }
    observed_summary = {
        "domains": candidate_record.get("domains", [])[:4],
        "observed_frequency": candidate_record.get("observed_frequency", 0),
        "discovery_rank": candidate_record.get("discovery_rank", 999),
        "discovery_role": discovery_record.get("candidate_role"),
        "discovery_reason": str(discovery_record.get("reason") or "")[:320],
        "discovery_confidence": discovery_record.get("confidence"),
    }

    return f"""
Validate this candidate against the immutable target scope in
{country["name"]} ({country["code"]}) at the time of this audit.

LOCKED TARGET SCOPE

{json.dumps(scope_summary, ensure_ascii=False)}

CANDIDATE

Name: {candidate_record["brand_name"]}
Domain: {candidate_record["representative_domain"]}
URL: {candidate_record["official_url"]}

DISCOVERY AND OBSERVED EVIDENCE

{json.dumps(observed_summary, ensure_ascii=False)}

The target scope is authoritative. Do not reject or reclassify the
target. Evaluate only whether the candidate matches it.

A valid direct competitor must:

1. Be active in the target country.
2. Operate in substantially the same category.
3. Have the same market role.
4. Use substantially the same business model.
5. Serve substantially the same primary customers.
6. Facilitate the same core transaction or selection decision.
7. Offer a realistic substitute.

Important distinctions:

- Marketplace and marketplace can be direct competitors.
- Aggregator/metasearch and marketplace are different roles.
- Inventory-owning dealer and marketplace are different roles.
- Publisher, directory, supplier, and downstream provider are not
  direct competitors unless the locked target has that exact role.

Inspect current public information and return only JSON:

{{
  "candidate_name": "canonical current name",
  "candidate_domain": "official domain",
  "official_url": "official URL",
  "candidate_category": "specific category",
  "candidate_role": "marketplace, aggregator_or_comparison, retailer_or_dealer, manufacturer, software_vendor, service_provider, publisher_or_directory, supplier_or_downstream, government, educational_resource, unrelated, or other",
  "candidate_business_model": "concise description",
  "active_in_target_country": true,
  "same_category": true,
  "same_market_role": true,
  "same_business_model": true,
  "same_primary_customers": true,
  "same_core_transaction": true,
  "offering_is_substitute": true,
  "is_direct_competitor": true,
  "market_prominence": 0.0,
  "reason": "concise explanation",
  "evidence": ["specific current public evidence"],
  "confidence": 0.0
}}

Return JSON only.
""".strip()


def core_discovery_supports_consistency_retry(
    candidate_record,
    scope,
    max_rank=LOCKED_SCOPE_CONFLICT_RETRY_MAX_RANK,
):
    discovery_record = (
        candidate_record.get(
            "discovery_record"
        )
        or {}
    )

    if not isinstance(discovery_record, dict):
        return False

    try:
        discovery_rank = int(
            candidate_record.get(
                "discovery_rank",
                999,
            )
            or 999
        )
    except (TypeError, ValueError):
        discovery_rank = 999

    if discovery_rank > max_rank:
        return False

    discovery_role = locked_scope_role(
        discovery_record.get(
            "candidate_role",
            "other",
        )
    )

    if discovery_role != scope["market_role"]:
        return False

    confidence = normalize_confidence(
        discovery_record.get(
            "confidence",
            candidate_record.get(
                "discovery_confidence",
                0.0,
            ),
        )
    )

    if confidence < (
        LOCKED_SCOPE_CONFLICT_RETRY_MIN_CONFIDENCE
    ):
        return False

    required_checks = (
        "active_in_target_country",
        "same_category",
        "same_market_role",
        "same_business_model",
        "same_primary_customers",
        "same_core_transaction",
        "offering_is_substitute",
    )

    if not all(
        normalize_boolean(
            discovery_record.get(
                field_name,
                False,
            )
        )
        for field_name in required_checks
    ):
        return False

    return bool(
        str(
            discovery_record.get(
                "reason",
                "",
            )
            or ""
        ).strip()
        or ensure_string_list(
            discovery_record.get(
                "evidence"
            )
        )
    )


def core_build_locked_scope_validation_retry_prompt(
    scope,
    candidate_record,
    initial_validation,
):
    scope_summary = {
        "brand_name": scope.get("brand_name"),
        "category": str(scope.get("category") or "")[:160],
        "market_role": scope.get("market_role"),
        "business_model": str(scope.get("business_model") or "")[:180],
        "primary_customers": [str(item)[:80] for item in (scope.get("primary_customers") or [])[:4]],
        "substitute_definition": str(scope.get("substitute_definition") or "")[:240],
        "country": scope.get("country"),
    }
    discovery = candidate_record.get("discovery_record") or {}
    discovery_summary = {
        "candidate_role": discovery.get("candidate_role"),
        "reason": str(discovery.get("reason") or "")[:320],
        "confidence": discovery.get("confidence"),
    }
    validation_summary = {
        key: initial_validation.get(key) for key in (
            "candidate_role", "is_direct_competitor", "failed_checks",
            "reason", "confidence",
        )
    }
    return f"""
Resolve a conflict between two earlier competitor assessments.
Independently verify current public information; do not simply vote or
defer to either assessment.

LOCKED TARGET SCOPE
{json.dumps(scope_summary, ensure_ascii=False)}

CANDIDATE
Name: {candidate_record["brand_name"]}
Domain: {candidate_record["representative_domain"]}
URL: {candidate_record["official_url"]}

HIGH-CONFIDENCE DISCOVERY ASSESSMENT
{json.dumps(discovery_summary, ensure_ascii=False)}

CONFLICTING INDIVIDUAL VALIDATION
{json.dumps(validation_summary, ensure_ascii=False)}

The target scope is immutable. Determine whether this candidate is an
active direct substitute in the target country with the same category,
market role, business model, primary customers, and core transaction.
Treat different wording as equivalent when the commercial function is
substantially the same. Do not broaden the category or market role.

Return only JSON with these exact fields:
{{
  "candidate_name": "canonical current name",
  "candidate_domain": "official domain",
  "official_url": "official URL",
  "candidate_category": "specific category",
  "candidate_role": "normalized market role",
  "candidate_business_model": "concise description",
  "active_in_target_country": true,
  "same_category": true,
  "same_market_role": true,
  "same_business_model": true,
  "same_primary_customers": true,
  "same_core_transaction": true,
  "offering_is_substitute": true,
  "is_direct_competitor": true,
  "market_prominence": 0.0,
  "reason": "concise evidence-based explanation",
  "evidence": ["specific current public evidence"],
  "confidence": 0.0
}}
""".strip()


def core_normalize_locked_scope_validation(
    data,
    candidate_record,
    scope,
    ports,
):
    get_root_domain = ports.get_root_domain
    normalize_public_url = ports.normalize_public_url
    data = core_canonical_candidate_validation_data(data, scope["market_role"])

    candidate_role = (
        locked_scope_role(
            data.get(
                "candidate_role",
                "other",
            )
        )
    )

    text = locked_scope_normalize_text(
        " ".join(
            [
                str(
                    data.get(
                        "reason",
                        "",
                    )
                ),
                str(
                    data.get(
                        "candidate_business_model",
                        "",
                    )
                ),
                " ".join(
                    ensure_string_list(
                        data.get(
                            "evidence"
                        )
                    )
                ),
            ]
        )
    )

    inactive_terms = [
        term
        for term in (
            LOCKED_SCOPE_INACTIVE_TERMS
        )
        if term in text
    ]

    checks = {
        "active_in_target_country": (
            normalize_boolean(
                data.get(
                    "active_in_target_country",
                    False,
                )
            )
        ),
        "same_category": (
            normalize_boolean(
                data.get(
                    "same_category",
                    False,
                )
            )
        ),
        "same_market_role": (
            normalize_boolean(
                data.get(
                    "same_market_role",
                    False,
                )
            )
        ),
        "same_business_model": (
            normalize_boolean(
                data.get(
                    "same_business_model",
                    False,
                )
            )
        ),
        "same_primary_customers": (
            normalize_boolean(
                data.get(
                    "same_primary_customers",
                    False,
                )
            )
        ),
        "same_core_transaction": (
            normalize_boolean(
                data.get(
                    "same_core_transaction",
                    False,
                )
            )
        ),
        "offering_is_substitute": (
            normalize_boolean(
                data.get(
                    "offering_is_substitute",
                    False,
                )
            )
        ),
        "ai_direct": (
            normalize_boolean(
                data.get(
                    "is_direct_competitor",
                    False,
                )
            )
        ),
    }

    role_matches_scope = (
        candidate_role
        == scope[
            "market_role"
        ]
    )

    if (
        scope["market_role"]
        == "other"
        and candidate_role
        not in LOCKED_SCOPE_REJECTED_ROLES
    ):
        role_matches_scope = (
            checks["same_market_role"]
        )

    if (
        candidate_role in LOCKED_SCOPE_REJECTED_ROLES
        and candidate_role
        != scope["market_role"]
    ):
        role_matches_scope = False

    if (
        scope["market_role"]
        == "marketplace"
        and candidate_role
        in {
            "aggregator_or_comparison",
            "retailer_or_dealer",
        }
    ):
        role_matches_scope = False

    validation_confidence = (
        normalize_confidence(
            data.get(
                "confidence"
            )
        )
    )

    discovery_confidence = (
        normalize_confidence(
            candidate_record.get(
                "discovery_confidence",
                0.0,
            )
        )
    )

    # Discovery and individual validation are independent AI checks.
    # A missing numeric score in one response must not veto seven
    # explicit scope matches confirmed by the other response.
    confidence = max(
        validation_confidence,
        discovery_confidence,
    )

    market_prominence = (
        normalize_confidence(
            data.get(
                "market_prominence"
            )
        )
    )

    valid = all(
        checks.values()
    ) and all(
        [
            role_matches_scope,
            not inactive_terms,
            confidence
            >= LOCKED_SCOPE_MIN_CONFIDENCE,
        ]
    )

    failed_checks = [
        name
        for name, passed
        in checks.items()
        if not passed
    ]

    reason = str(
        data.get(
            "reason",
            "",
        )
        or ""
    ).strip()

    if inactive_terms:
        reason = (
            "Candidate is inactive or "
            "discontinued: "
            + ", ".join(
                inactive_terms
            )
        )

    elif not role_matches_scope:
        reason = (
            f"Candidate role "
            f"{candidate_role!r} does not "
            f"match locked target role "
            f"{scope['market_role']!r}."
        )

    elif failed_checks:
        reason = (
            "Candidate failed locked-scope "
            "requirements: "
            + ", ".join(
                failed_checks
            )
        )

    official_url = (
        normalize_public_url(
            data.get(
                "official_url"
            )
            or candidate_record[
                "official_url"
            ]
        )
        or candidate_record[
            "official_url"
        ]
    )

    domain = get_root_domain(
        data.get(
            "candidate_domain"
        )
        or official_url
        or candidate_record[
            "representative_domain"
        ]
    )

    return {
        "candidate_name": str(
            data.get(
                "candidate_name"
            )
            or candidate_record[
                "brand_name"
            ]
            or domain
        ).strip(),
        "candidate_domain": (
            domain
            or candidate_record[
                "representative_domain"
            ]
        ),
        "official_url": official_url,
        "candidate_category": str(
            data.get(
                "candidate_category",
                "",
            )
        ).strip(),
        "candidate_role": (
            candidate_role
        ),
        "candidate_business_model": str(
            data.get(
                "candidate_business_model",
                "",
            )
        ).strip(),
        "locked_target_role": (
            scope["market_role"]
        ),
        "role_matches_scope": (
            role_matches_scope
        ),
        **checks,
        "is_direct_competitor": (
            valid
        ),
        "market_prominence": (
            market_prominence
        ),
        "reason": reason,
        "evidence": (
            ensure_string_list(
                data.get(
                    "evidence"
                )
            )[:5]
        ),
        "confidence": confidence,
        "validation_confidence": (
            validation_confidence
        ),
        "discovery_confidence": (
            discovery_confidence
        ),
        "failed_checks": failed_checks,
        "inactive_terms": (
            inactive_terms
        ),
    }
