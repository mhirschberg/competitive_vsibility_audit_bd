"""Profile prompt, normalization, and Bright Data snapshot adapters.

All model construction, URL parsing, and provider operations are explicit
inputs. The functions can therefore run in the hosted service or be embedded
in the standalone notebook without depending on either runtime directly.
"""

import re


def build_profile_prompt_core(job, target_brand, audit_focus=""):
    audit_focus = str(audit_focus or "").strip()
    if job["role"] == "target":
        role_instruction = (
            "This is the audited target. Describe the current "
            "offering and how it is positioned for customers."
        )
        direct_competitor = "false"
    else:
        role_instruction = (
            f"This is being evaluated as an alternative to "
            f"{target_brand.brand_name}. Focus on why a customer "
            f"might compare the two. Selection reason: "
            f"{job['reason']}"
        )
        direct_competitor = "true"

    if audit_focus:
        focus_instruction = f"""
AUDIT SCOPE — STRICT REQUIREMENT

The audit is specifically about: {audit_focus}

Scope the entire profile to this focus. Include only the category,
positioning, customers, products or services, features, differentiators,
and evidence that directly support this focus or a substitutable
alternative to it. Exclude unrelated business lines even when they are
prominent on the website. If the public evidence does not support a
field within this scope, leave it empty or use unknown rather than
filling it with an unrelated offering.
""".strip()
    else:
        focus_instruction = (
            "No narrower audit focus was supplied. "
            "Profile the primary offering represented by the website."
        )

    return f"""
Analyze this current public website.

Name: {job["brand_name"]}
Website: {job["official_url"]}
Domain: {job["domain"]}

{role_instruction}

{focus_instruction}

Adapt the analysis to the actual category. Relevant details may include
products, services, benefits, features, claims, ingredients,
specifications, use cases, audience, price, availability, proof,
reviews, trust signals, location, or delivery model.

Return only JSON:

{{
  "brand_name": "canonical brand, product, service, or organization",
  "official_url": "{job["official_url"]}",
  "domain": "{job["domain"]}",
  "category": "specific category",
  "positioning": "one customer-facing sentence",
  "target_customers": ["customer, user, or audience"],
  "relevant_products": ["relevant product, service, or offering"],
  "key_features": ["feature, benefit, claim, ingredient, or attribute"],
  "differentiators": ["meaningful differentiator"],
  "pricing_model": "price, price tier, pricing approach, or unknown",
  "competitor_reason": "why customers would compare it",
  "direct_competitor": {direct_competitor},
  "confidence": 0.0,
  "evidence": ["specific public evidence"]
}}

Keep lists to five items or fewer. Do not invent claims or pricing.
Return JSON only without Markdown fences.
""".strip()


def clean_profile_label_core(value):
    text = " ".join(str(value or "").split()).strip()
    if text.startswith("[") and "](" in text:
        text = text[1:].split("](", 1)[0].strip()
    else:
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(
        r"\s*Go to product viewer dialog for this item\.?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip(" []()\t\r\n-–—,.;")


def normalize_brand_profile_core(
    data,
    job,
    *,
    profile_factory,
    normalize_public_url,
    get_root_domain,
    ensure_string_list,
    normalize_confidence,
):
    if not isinstance(data, dict):
        data = {}

    raw_name = str(
        data.get("brand_name") or data.get("name") or job["brand_name"]
    ).strip()
    name = clean_profile_label_core(raw_name)
    if raw_name != name and job.get("brand_name"):
        name = clean_profile_label_core(job["brand_name"])
    if not name:
        name = clean_profile_label_core(job["brand_name"])

    official_url = normalize_public_url(
        data.get("official_url") or data.get("website") or job["official_url"]
    )
    domain = get_root_domain(
        data.get("domain") or official_url or job["domain"]
    )
    normalized = {
        "brand_name": name,
        "official_url": official_url or job["official_url"],
        "domain": domain or job["domain"],
        "category": str(data.get("category") or "").strip(),
        "positioning": str(data.get("positioning") or "").strip(),
        "target_customers": ensure_string_list(
            data.get("target_customers")
        )[:5],
        "relevant_products": [
            cleaned
            for item in ensure_string_list(
                data.get("relevant_products") or data.get("products")
            )[:5]
            if (cleaned := clean_profile_label_core(item))
        ],
        "key_features": ensure_string_list(data.get("key_features"))[:5],
        "differentiators": ensure_string_list(data.get("differentiators"))[:5],
        "pricing_model": str(data.get("pricing_model") or "unknown").strip(),
        "competitor_reason": (
            "Target company"
            if job["role"] == "target"
            else str(
                data.get("competitor_reason") or job.get("reason") or ""
            ).strip()
        ),
        "direct_competitor": job["role"] == "competitor",
        "confidence": normalize_confidence(data.get("confidence")),
        "evidence": ensure_string_list(data.get("evidence"))[:5],
    }
    return profile_factory(**normalized)


def generate_profile_sync_core(
    job,
    target_brand,
    audit_focus="",
    *,
    client,
    parse_ai_json,
    normalize_profile,
    snapshot_timeout_error,
):
    prompt = build_profile_prompt_core(job, target_brand, audit_focus)
    try:
        record = client.google_ai_mode(prompt, timeout_seconds=600)
        profile = normalize_profile(parse_ai_json(client.answer_text(record)), job)
        return {
            "status": "success", "job": job, "profile": profile,
            "record": record, "prompt": prompt, "error": None,
            "snapshot_id": None,
        }
    except snapshot_timeout_error as exc:
        return {
            "status": "pending", "job": job, "profile": None,
            "record": None, "prompt": prompt, "error": str(exc),
            "snapshot_id": exc.snapshot_id,
        }
    except Exception as exc:
        return {
            "status": "failed", "job": job, "profile": None,
            "record": None, "prompt": prompt, "error": str(exc),
            "snapshot_id": None,
        }


def recover_profile_sync_core(
    task_result,
    *,
    client,
    parse_ai_json,
    normalize_profile,
    provider_error,
):
    snapshot_id = task_result["snapshot_id"]
    try:
        records = client.wait_for_snapshot(snapshot_id, timeout_seconds=600)
        for record in records:
            answer = client.answer_text(record)
            if not answer:
                continue
            profile = normalize_profile(parse_ai_json(answer), task_result["job"])
            return {
                **task_result, "status": "success", "profile": profile,
                "record": record, "error": None,
            }
        raise provider_error("Recovered snapshot returned no answer text.")
    except Exception as exc:
        return {**task_result, "status": "failed", "error": str(exc)}


def fallback_profile_core(job, target_brand, *, profile_factory):
    if job["role"] == "target":
        values = {
            "brand_name": target_brand.brand_name,
            "official_url": target_brand.official_url,
            "domain": target_brand.domain,
            "category": target_brand.category,
            "positioning": target_brand.positioning,
            "target_customers": target_brand.target_customers,
            "relevant_products": target_brand.products,
            "key_features": target_brand.key_features,
            "differentiators": target_brand.differentiators,
            "pricing_model": "unknown",
            "competitor_reason": "Target company",
            "direct_competitor": False,
            "confidence": target_brand.confidence,
            "evidence": target_brand.evidence,
        }
    else:
        values = {
            "brand_name": job["brand_name"],
            "official_url": job["official_url"],
            "domain": job["domain"],
            "category": "",
            "positioning": "",
            "target_customers": [],
            "relevant_products": [],
            "key_features": [],
            "differentiators": [],
            "pricing_model": "unknown",
            "competitor_reason": job["reason"],
            "direct_competitor": True,
            "confidence": 0.0,
            "evidence": [],
        }
    return profile_factory(**values)
