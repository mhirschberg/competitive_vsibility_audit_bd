"""Provider-neutral orchestration for company research and keyword setup."""

import json


# SERVICE-ONLY-IMPORTS: start
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
