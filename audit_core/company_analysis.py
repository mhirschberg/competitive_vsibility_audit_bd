"""Provider-neutral orchestration for company research and keyword setup."""

import json
import re


# SERVICE-ONLY-IMPORTS: start
from .company_models import BuyerIntentKeyword, CompanyIntake
from .domains import get_root_domain
from .domains import normalize_public_url
from .primitives import ensure_string_list, normalize_confidence
from .ai_localization import market_language
# SERVICE-ONLY-IMPORTS: end


class CompanyAnalysisPorts:
    def __init__(
        self, *, client, run_utility, parse_json, normalize_intake,
        select_relevant_research, complete_keywords, proofread_keywords,
        build_locked_scope, error_type,
    ):
        self.client = client
        self.run_utility = run_utility
        self.parse_json = parse_json
        self.normalize_intake = normalize_intake
        self.select_relevant_research = select_relevant_research
        self.complete_keywords = complete_keywords
        self.proofread_keywords = proofread_keywords
        self.build_locked_scope = build_locked_scope
        self.error_type = error_type


def normalize_keyword_records(raw_keywords):
    """Normalize keyword strings and mappings without applying AI/schema rules."""
    if isinstance(raw_keywords, str):
        raw_keywords = [
            item.strip()
            for item in raw_keywords.split(",")
            if item.strip()
        ]

    if not isinstance(raw_keywords, list):
        return []

    normalized = []
    seen = set()

    for item in raw_keywords:
        if isinstance(item, str):
            keyword = item.strip()
            record = {
                "keyword": keyword,
                "intent": "commercial",
                "rationale": "",
            }
        elif isinstance(item, dict):
            keyword = str(
                item.get("keyword")
                or item.get("query")
                or item.get("term")
                or ""
            ).strip()
            record = {
                "keyword": keyword,
                "intent": str(item.get("intent") or "commercial").strip(),
                "rationale": str(
                    item.get("rationale") or item.get("reason") or ""
                ).strip(),
            }
        else:
            continue

        key = keyword.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(record)

    return normalized


def prepare_company_intake_payload(
    data, company_name, company_url, *, normalize_public_url,
    get_root_domain, ensure_string_list, normalize_confidence,
):
    """Normalize company fields into a plain payload before schema validation."""
    if not isinstance(data, dict):
        raise ValueError("Company analysis must be a JSON object.")

    if "brand" not in data:
        brand_keys = {
            "brand_name", "official_url", "domain", "category",
            "description", "positioning", "primary_market_role",
            "secondary_market_roles", "offering_type", "value_chain_position",
            "substitute_definition", "classification_confidence",
            "classification_evidence", "target_customers", "products",
            "key_features", "differentiators", "confidence", "evidence",
        }
        data["brand"] = {
            key: data[key] for key in data if key in brand_keys
        }

    brand = data.get("brand") or {}
    if not isinstance(brand, dict):
        brand = {}

    official_url = normalize_public_url(
        brand.get("official_url") or company_url
    )
    if not official_url:
        official_url = normalize_public_url(company_url)
    domain = get_root_domain(brand.get("domain") or official_url)

    brand["brand_name"] = str(
        brand.get("brand_name") or company_name
    ).strip()
    if not brand["brand_name"]:
        brand["brand_name"] = company_name
    brand["official_url"] = official_url
    brand["domain"] = domain

    for field_name in (
        "category", "description", "positioning", "primary_market_role",
        "offering_type", "value_chain_position", "substitute_definition",
    ):
        brand[field_name] = str(brand.get(field_name) or "").strip()

    for field_name in (
        "target_customers", "products", "key_features", "differentiators",
        "evidence", "secondary_market_roles", "classification_evidence",
    ):
        brand[field_name] = ensure_string_list(brand.get(field_name))[:8]

    brand["confidence"] = normalize_confidence(brand.get("confidence"))
    brand["classification_confidence"] = normalize_confidence(
        brand.get("classification_confidence")
    )
    keywords = normalize_keyword_records(
        data.get("buyer_intent_keywords") or data.get("keywords") or []
    )
    return {"brand": brand, "buyer_intent_keywords": keywords}


def normalize_company_intake_core(
    data, company_name, company_url, *, intake_model=None,
):
    """Normalize company input and validate it with the shared intake schema."""
    model = intake_model or CompanyIntake
    payload = prepare_company_intake_payload(
        data,
        company_name,
        company_url,
        normalize_public_url=normalize_public_url,
        get_root_domain=get_root_domain,
        ensure_string_list=ensure_string_list,
        normalize_confidence=normalize_confidence,
    )
    validator = getattr(model, "model_validate", None)
    if callable(validator):
        return validator(payload)
    return model.parse_obj(payload)


def build_company_keyword_completion_prompt(settings, brand, current_keywords):
    """Build the prompt used to complete a short buyer-keyword set."""
    existing = [item.keyword for item in current_keywords]
    audit_focus = str(settings.get("audit_focus", "") or "").strip()
    return f"""
Using only the supplied information, return exactly eight unique
non-branded buyer-intent searches appropriate for this market.

Category: {brand.category}
Audit focus: {audit_focus or "primary offering"}
Positioning: {brand.positioning}
Offerings: {", ".join(brand.products[:5])}
Attributes or benefits: {", ".join(brand.key_features[:6])}

Existing keywords:
{json.dumps(existing, ensure_ascii=False)}

The searches should sound like something a real customer would enter
when looking for, evaluating, comparing, or buying alternatives.

They may be consumer, B2B, local, commercial, transactional, or
solution-evaluation searches depending on the category.

Return only JSON:

{{
  "buyer_intent_keywords": [
    {{
      "keyword": "buyer query",
      "intent": "commercial",
      "rationale": "short reason"
    }}
  ]
}}

Do not include the audited brand or competitor names.
""".strip()


def complete_company_keywords_core(
    settings, brand, current_keywords, *, run_utility, parse_json,
    model_to_dict, keyword_model=None,
):
    """Complete a short keyword set while preserving measured AI provenance."""
    prompt = build_company_keyword_completion_prompt(
        settings, brand, current_keywords,
    )
    result = run_utility(prompt)
    parsed = parse_json(result["answer"])
    completed = normalize_keyword_records(
        parsed.get("buyer_intent_keywords") or parsed.get("keywords") or []
    )

    combined = []
    seen = set()
    audited_name = settings["company_name"].lower().strip()
    model = keyword_model or BuyerIntentKeyword
    for item in [
        *[model_to_dict(keyword) for keyword in current_keywords],
        *completed,
    ]:
        keyword = str(item.get("keyword") or "").strip()
        key = keyword.lower()
        if not key or key in seen or audited_name in key:
            continue
        seen.add(key)
        validator = getattr(model, "model_validate", None)
        combined.append(
            validator(item) if callable(validator) else model.parse_obj(item)
        )
        if len(combined) == 8:
            break

    return {
        "keywords": combined,
        "record": result["record"],
        "snapshot_id": result["snapshot_id"],
    }


GENERIC_KEYWORD_PLACEHOLDERS = {
    "primary offering", "main offering", "core offering",
    "products and services", "product and service", "product options",
    "service options", "offering options", "buy products",
    "purchase products", "purchase services", "buy services",
    "best product options", "best service options", "best products",
    "best services", "company products", "company services",
    "business solutions", "available products", "available services",
}

KEYWORD_PROOFREADING_STOPWORDS = {
    "a", "an", "and", "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "einer", "einem", "einen", "für", "im", "in",
    "mit", "of", "on", "or", "the", "to", "und", "von", "zu",
}


def normalize_keyword_for_quality(keyword):
    return re.sub(r"\s+", " ", str(keyword or "").strip().lower())


def is_generic_placeholder_keyword(keyword):
    normalized = normalize_keyword_for_quality(keyword)
    if not normalized or normalized in GENERIC_KEYWORD_PLACEHOLDERS:
        return True
    return normalized in {
        "products", "services", "solutions", "offerings", "options",
        "companies", "providers", "suppliers",
    } if len(normalized.split()) == 1 else False


def keyword_meaningful_tokens(keyword):
    return {
        token for token in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", str(keyword or "").lower())
        if len(token) >= 3 and token not in KEYWORD_PROOFREADING_STOPWORDS
    }


def keyword_proofreading_is_safe(original_keywords, corrected_records, company_name):
    if len(corrected_records) != 8:
        return {"valid": False, "reason": "Proofreader did not return exactly eight keywords."}

    corrected_keywords = [
        str(item.get("keyword", "")).strip() for item in corrected_records
    ]
    normalized = [
        re.sub(r"\s+", " ", keyword.lower()).strip()
        for keyword in corrected_keywords
    ]
    if any(not keyword for keyword in normalized):
        return {"valid": False, "reason": "Proofreader returned an empty keyword."}
    if len(set(normalized)) != 8:
        return {"valid": False, "reason": "Proofreader returned duplicate keywords."}

    company_name = str(company_name or "").strip().lower()
    if company_name and any(company_name in keyword for keyword in normalized):
        return {"valid": False, "reason": "Proofreader inserted the audited brand name."}

    generic = [keyword for keyword in normalized if is_generic_placeholder_keyword(keyword)]
    if generic:
        return {
            "valid": False,
            "reason": "Proofreader returned generic keywords: " + ", ".join(generic),
        }

    for original, corrected in zip(original_keywords, corrected_keywords):
        original_tokens = keyword_meaningful_tokens(original)
        corrected_tokens = keyword_meaningful_tokens(corrected)
        if original_tokens and corrected_tokens and not (original_tokens & corrected_tokens):
            return {
                "valid": False,
                "reason": (
                    "Proofreading changed query intent too much: "
                    f"{original!r} -> {corrected!r}"
                ),
            }
    return {
        "valid": True,
        "reason": "Eight unique, non-branded, intent-preserving keywords.",
    }


def build_buyer_keyword_proofreading_prompt(
    settings, brand, original_records, *, market_language_fn,
):
    country_code = str(settings.get("country", "") or "").upper()
    language = market_language_fn(country_code)
    return f"""
Proofread these eight buyer search queries.

Target country: {country_code}
Required search language: {language}
Category: {brand.category}
Audit focus: {settings.get("audit_focus", "") or "primary offering"}

Current queries:

{json.dumps(original_records, ensure_ascii=False)}

Rules:

- Return exactly eight queries in the same order.
- Preserve the commercial intent and meaning of each query.
- Correct spelling, grammar, malformed words, and unnatural phrasing.
- Make each query sound like something a real customer would search.
- Do not add the audited brand or competitor names.
- Do not broaden, replace, merge, or split query intents.
- Keep rationales concise and in English.

Return only JSON:

{{
  "buyer_intent_keywords": [
    {{
      "keyword": "proofread buyer query",
      "intent": "commercial",
      "rationale": "short English rationale"
    }}
  ]
}}
""".strip()


def proofread_buyer_keywords_core(
    settings, brand, current_keywords, *, run_utility, parse_json,
    model_to_dict, market_language_fn=None, keyword_model=None,
):
    """Proofread buyer keywords, applying changes only after safety checks."""
    original_records = [model_to_dict(item) for item in current_keywords]
    original_keywords = [item["keyword"] for item in original_records]
    if len(original_keywords) != 8:
        return {
            "keywords": current_keywords,
            "status": "skipped",
            "reason": "Keyword set did not contain exactly eight items.",
            "record": None,
            "snapshot_id": None,
        }

    market_language_fn = market_language_fn or market_language
    prompt = build_buyer_keyword_proofreading_prompt(
        settings,
        brand,
        original_records,
        market_language_fn=market_language_fn,
    )
    try:
        result = run_utility(prompt, timeout_seconds=900)
        parsed = parse_json(result["answer"])
        corrected_records = normalize_keyword_records(
            parsed.get("buyer_intent_keywords") or parsed.get("keywords") or []
        )
        validation = keyword_proofreading_is_safe(
            original_keywords, corrected_records, brand.brand_name,
        )
        if not validation["valid"]:
            return {
                "keywords": current_keywords,
                "status": "rejected",
                "reason": validation["reason"],
                "record": result.get("record"),
                "snapshot_id": result.get("snapshot_id"),
            }

        model = keyword_model or BuyerIntentKeyword
        corrected_models = []
        for original, corrected in zip(original_records, corrected_records):
            corrected_item = dict(corrected)
            if not corrected_item.get("intent"):
                corrected_item["intent"] = original.get("intent", "commercial")
            if not corrected_item.get("rationale"):
                corrected_item["rationale"] = original.get("rationale", "")
            validator = getattr(model, "model_validate", None)
            corrected_models.append(
                validator(corrected_item)
                if callable(validator) else model.parse_obj(corrected_item)
            )

        return {
            "keywords": corrected_models,
            "status": "applied",
            "reason": validation["reason"],
            "record": result.get("record"),
            "snapshot_id": result.get("snapshot_id"),
            "original_keywords": original_keywords,
            "corrected_keywords": [item.keyword for item in corrected_models],
        }
    except Exception as exc:
        return {
            "keywords": current_keywords,
            "status": "failed",
            "reason": f"{type(exc).__name__}: {exc}",
            "record": None,
            "snapshot_id": None,
        }


def build_company_research_prompt(settings):
    """Ask broad, category-neutral questions about the audited company."""
    audit_focus = str(settings.get("audit_focus", "") or "").strip()
    focus_instruction = (
        f"Specific audit focus: {audit_focus}"
        if audit_focus else
        "Audit focus: infer the primary product, service, offering, or "
        "customer need represented by the website."
    )
    return f"""
Analyze the current public website for this organization or brand.

Name: {settings["company_name"]}
Website: {settings["company_url"]}
Country: {settings["country"]}
{focus_instruction}

First determine what kind of market this is, such as consumer product,
B2B product, software, professional service, local business,
health/beauty product, retailer, financial product, education,
hospitality, or another category.

Provide a concise research brief covering:

- Canonical brand, organization, or product name
- The specific product, service, or offering being audited
- Market and product category
- Intended customer, user, or audience
- Primary customer need or problem addressed
- Main products, services, or alternatives offered
- Important features, benefits, claims, or capabilities
- Relevant proof, trust signals, ingredients, specifications, or
  evidence when applicable
- Meaningful differentiators
- Price, price tier, pricing approach, or availability when public
- The criteria a real customer would use to compare alternatives
- Exactly eight non-branded buyer-intent searches that could be used
  to find this offering and competing alternatives

The buyer searches must match the actual market. They may be consumer,
commercial, transactional, local, or solution-evaluation searches.

Do not include the brand name or competitor names in the searches.

Use current public information. Keep the response concise. Do not ask
follow-up questions.
""".strip()


def build_company_structuring_prompt(
    settings, research_text, *, select_relevant_research, strict_retry=False,
):
    """Turn the research into the stable brand and keyword JSON schema."""
    audit_focus = str(settings.get("audit_focus", "") or "").strip()
    relevant_research = select_relevant_research(
        research_text=research_text,
        company_name=settings["company_name"],
        company_domain=settings["company_domain"],
        audit_focus=audit_focus,
        max_characters=2400,
    )
    retry_instruction = (
        "A previous formatting attempt failed. Return the JSON object directly."
        if strict_retry else ""
    )
    prompt = f"""
Structure the supplied company research. Do not perform new research.

Known company: {settings["company_name"]}
Known URL: {settings["company_url"]}
Known domain: {settings["company_domain"]}
Audit focus: {audit_focus or "infer the primary offering"}

RESEARCH
--------
{relevant_research}
--------
END RESEARCH

Return only JSON:

{{
  "brand": {{
    "brand_name": "canonical name",
    "official_url": "{settings["company_url"]}",
    "domain": "{settings["company_domain"]}",
    "category": "specific market category",
    "description": "one or two sentences",
    "positioning": "customer-facing positioning",
    "target_customers": ["specific buyer or audience"],
    "products": ["specific product, service, or offering"],
    "key_features": ["specific feature, benefit, claim, or attribute"],
    "differentiators": ["meaningful differentiator"],
    "confidence": 0.0,
    "evidence": ["evidence from the supplied research"]
  }},
  "buyer_intent_keywords": [
    {{
      "keyword": "specific non-branded buyer search",
      "intent": "commercial",
      "rationale": "short reason"
    }}
  ]
}}

Requirements:
- Return exactly eight unique buyer searches.
- Every search must clearly relate to the company's actual market.
- Do not use generic placeholders such as products and services,
  primary offering, product options, service options, or buy products.
- Do not include the audited company name.
- Do not invent unsupported information.
- Return JSON only.

{retry_instruction}
""".strip()
    if len(prompt) > 3900:
        raise ValueError(
            f"Company structuring prompt is too long: {len(prompt)} characters."
        )
    return prompt


def select_relevant_company_research(
    research_text, company_name, company_domain, audit_focus="",
    max_characters=2400,
):
    """Select high-signal research blocks while retaining all eight queries."""
    text = str(research_text or "").strip()
    if len(text) <= max_characters:
        return text

    buyer_queries = []
    heading = re.search(r"buyer[- ]intent searches|buyer searches", text, re.I)
    if heading:
        buyer_queries = re.findall(
            r"(?m)^\s*\d{1,2}[.)]\s+([^\n]+)",
            text[heading.end():],
        )[:8]
    buyer_excerpt = ""
    if len(buyer_queries) == 8:
        buyer_excerpt = "Research-proposed buyer searches:\n" + "\n".join(
            f"{index}. {query.strip()}"
            for index, query in enumerate(buyer_queries, 1)
        )
    selection_budget = max_characters - len(buyer_excerpt) - 2

    company_name_lower = str(company_name or "").strip().lower()
    domain_stem = get_root_domain(company_domain).split(".")[0].lower()
    focus_terms = set(re.findall(r"[a-z0-9]{4,}", str(audit_focus or "").lower()))
    useful_terms = {
        "company", "category", "market", "product", "products", "service",
        "services", "customers", "customer", "buyers", "audience",
        "positioning", "offering", "offerings", "features", "benefits",
        "differentiators", "manufacturer", "provider", "platform",
        "specializes", "specialization",
    }
    blocks = [
        block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()
    ]
    if len(blocks) < 4:
        blocks = [text[index:index + 600] for index in range(0, len(text), 600)]

    scored_blocks = []
    for index, block in enumerate(blocks):
        lowered = block.lower()
        score = 0
        if company_name_lower and company_name_lower in lowered:
            score += 20
        if domain_stem and domain_stem in lowered:
            score += 12
        score += sum(5 for term in focus_terms if term in lowered)
        score += sum(1 for term in useful_terms if term in lowered)
        if lowered.count("http://") + lowered.count("https://") >= 3:
            score -= 5
        scored_blocks.append((score, index, block))

    scored_blocks.sort(key=lambda item: (-item[0], item[1]))
    selected = []
    used_characters = 0
    for score, index, block in scored_blocks:
        if score <= 0 and selected:
            continue
        remaining = selection_budget - used_characters
        if remaining <= 100:
            break
        selected.append((index, block[:remaining]))
        used_characters += len(selected[-1][1]) + 2

    selected.sort(key=lambda item: item[0])
    result = "\n\n".join(block for _, block in selected).strip()
    if buyer_excerpt:
        result = (result + "\n\n" + buyer_excerpt).strip()
    if not result:
        result = text[:max_characters]
    return result[:max_characters]


def run_company_analysis_core(settings, *, ports):
    """Research a company, structure the response, and finish keyword checks."""
    client = ports.client
    client.log("Starting Google AI Mode company research")
    research_prompt = build_company_research_prompt(settings)
    research_record = client.google_ai_mode(
        research_prompt, timeout_seconds=720,
    )
    research_text = client.answer_text(research_record)
    if not research_text:
        raise ports.error_type("Google AI Mode returned no company research text.")
    client.log(f"Google AI Mode research returned {len(research_text):,} characters")

    structuring_errors = []
    structured_result = None
    intake = None
    for attempt in (1, 2):
        client.log(f"Starting ChatGPT structuring attempt {attempt}/2")
        prompt = build_company_structuring_prompt(
            settings,
            research_text,
            select_relevant_research=ports.select_relevant_research,
            strict_retry=attempt == 2,
        )
        if getattr(client, "debug", False):
            relevant_research = ports.select_relevant_research(
                research_text=research_text,
                company_name=settings["company_name"],
                company_domain=settings["company_domain"],
                audit_focus=str(settings.get("audit_focus", "") or "").strip(),
                max_characters=2400,
            )
            client.log(
                f"Company structuring prompt: {len(prompt)} characters; "
                f"selected research: {len(relevant_research)} characters"
            )
        try:
            candidate_result = ports.run_utility(prompt)
            parsed = ports.parse_json(candidate_result["answer"])
            candidate_intake = ports.normalize_intake(
                data=parsed,
                company_name=settings["company_name"],
                company_url=settings["company_url"],
            )
            structured_result = candidate_result
            intake = candidate_intake
            break
        except Exception as exc:
            structuring_errors.append(
                f"Attempt {attempt}: {type(exc).__name__}: {exc}"
            )
            client.log(f"ChatGPT structuring attempt {attempt} failed: {exc}", "yellow")

    if intake is None:
        raise ports.error_type(
            "ChatGPT could not structure the Google AI Mode research.\n- "
            + "\n- ".join(structuring_errors)
        )

    keyword_completion = None
    if len(intake.buyer_intent_keywords) != 8:
        client.log(
            f"Structured result contained {len(intake.buyer_intent_keywords)} "
            "keywords; completing the set"
        )
        keyword_completion = ports.complete_keywords(
            settings=settings,
            brand=intake.brand,
            current_keywords=intake.buyer_intent_keywords,
        )
        intake.buyer_intent_keywords = keyword_completion["keywords"]

    if len(intake.buyer_intent_keywords) != 8:
        raise ports.error_type(
            "The company-analysis workflow produced "
            f"{len(intake.buyer_intent_keywords)} keywords instead of eight."
        )

    locked_scope = ports.build_locked_scope(intake.brand, settings)
    proofreading = ports.proofread_keywords(
        settings=settings,
        brand=intake.brand,
        current_keywords=intake.buyer_intent_keywords,
    )
    intake.buyer_intent_keywords = proofreading["keywords"]
    result = {
        "intake": intake,
        "record": research_record,
        "prompt": research_prompt,
        "research_text": research_text,
        "structuring_record": structured_result["record"],
        "structuring_snapshot_id": structured_result["snapshot_id"],
        "keyword_completion": keyword_completion,
        "workflow": "google_ai_research_chatgpt_structuring",
        "locked_target_scope": dict(locked_scope),
        "keyword_proofreading": {
            key: value for key, value in proofreading.items()
            if key not in {"keywords", "record"}
        },
    }
    if isinstance(proofreading.get("record"), dict):
        result["keyword_proofreading_record"] = proofreading["record"]
    if proofreading.get("status") not in {"applied", "skipped"}:
        client.log(
            f"Buyer-keyword proofreading {proofreading.get('status')}: "
            f"{proofreading.get('reason')}",
            "yellow",
        )
    return result
