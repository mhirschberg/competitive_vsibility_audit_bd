"""Neutral category-level prompt used for measured AI visibility."""


def build_visibility_prompt_core(target_profile, keywords, audit_focus=""):
    category = target_profile.category or "product or service category"
    audit_focus = str(audit_focus or "").strip()
    keyword_text = "; ".join(keywords)

    prompt = f"""
I am evaluating alternatives in this category:

{category}

Specific need or focus:
{audit_focus or "the needs represented by the searches below"}

Customer searches and requirements:

{keyword_text}

Recommend the leading brands, products, services, providers, or
organizations a real customer should consider.

Compare them using criteria that actually matter in this category.
These may include suitability, benefits, quality, evidence, claims,
ingredients, specifications, features, price, availability,
reputation, service model, performance, ease of use, or other
category-relevant factors.

Ignore criteria that are irrelevant to this market.

Use current public web information. Provide an independent shortlist.
Do not ask follow-up questions.
""".strip()

    if len(prompt) > 4096:
        raise ValueError(
            f"AI visibility prompt is too long: {len(prompt)} characters."
        )

    return prompt
