"""Task-aware validation shared by the notebook and hosted research race."""

# SERVICE-ONLY-IMPORTS: start
# SERVICE-ONLY-IMPORTS: end


MIN_NARRATIVE_CHARACTERS = 120


def identify_research_task(prompt):
    """Infer the expected response shape from the established prompt text."""
    prompt_lower = str(prompt or "").lower()
    asks_for_json = any(
        marker in prompt_lower
        for marker in (
            "return only json",
            "return json only",
            "return the json object",
            "return only:",
        )
    )

    if (
        asks_for_json
        and '"competitors"' in prompt_lower
        and "rank_by_directness" in prompt_lower
    ):
        return "competitor_selection_json"
    if (
        asks_for_json
        and '"candidate_name"' in prompt_lower
        and '"is_direct_competitor"' in prompt_lower
    ):
        return "candidate_validation_json"
    if (
        asks_for_json
        and '"brand_name"' in prompt_lower
        and '"relevant_products"' in prompt_lower
    ):
        return "brand_profile_json"
    if asks_for_json:
        return "generic_json"
    if "a customer is researching this need" in prompt_lower:
        return "customer_question_research"
    if (
        "analyze the current public website" in prompt_lower
        or "analyze this current public website" in prompt_lower
    ):
        return "website_research"
    return "narrative_research"


def validate_research_answer(
    answer,
    prompt,
    *,
    parse_json,
    remove_boilerplate,
    min_narrative_characters=MIN_NARRATIVE_CHARACTERS,
):
    """Validate JSON structure or substantive narrative research content."""
    task_type = identify_research_task(prompt)
    answer = str(answer or "").strip()
    if not answer:
        return {"valid": False, "task_type": task_type, "reason": "Answer was empty."}

    if task_type.endswith("_json"):
        try:
            parsed = parse_json(answer)
        except Exception as exc:
            return {
                "valid": False,
                "task_type": task_type,
                "reason": f"Answer was not parseable JSON: {type(exc).__name__}: {exc}",
            }
        if not isinstance(parsed, dict):
            return {
                "valid": False,
                "task_type": task_type,
                "reason": "Parsed JSON was not an object.",
            }

        if task_type == "competitor_selection_json":
            competitors = parsed.get("competitors") or parsed.get("selected_competitors") or []
            valid_records = [
                item for item in competitors
                if isinstance(item, dict) and (item.get("domain") or item.get("official_url"))
            ]
            if len(valid_records) < 2:
                return {
                    "valid": False,
                    "task_type": task_type,
                    "reason": "Competitor-selection JSON contained fewer than two competitor records.",
                    "parsed": parsed,
                }
        elif task_type == "candidate_validation_json":
            if not any(key in parsed for key in (
                "candidate_name", "candidate_domain", "candidate_type",
                "is_direct_competitor",
            )):
                return {
                    "valid": False,
                    "task_type": task_type,
                    "reason": "Candidate-validation JSON did not contain validation fields.",
                    "parsed": parsed,
                }
        elif task_type == "brand_profile_json":
            if not any(parsed.get(key) for key in (
                "brand_name", "name", "domain", "official_url",
            )):
                return {
                    "valid": False,
                    "task_type": task_type,
                    "reason": "Profile JSON did not contain brand identity fields.",
                    "parsed": parsed,
                }

        return {
            "valid": True,
            "task_type": task_type,
            "reason": "Valid JSON research answer",
            "parsed": parsed,
        }

    cleaned = str(remove_boilerplate(answer) or "").strip()
    if len(cleaned) < min_narrative_characters:
        return {
            "valid": False,
            "task_type": task_type,
            "reason": f"Narrative answer was too short: {len(cleaned)} characters.",
        }

    normalized = " ".join(cleaned.lower().split())
    interface_only_values = {
        "log in", "login", "sign up", "sign up for free",
        "something went wrong", "try again",
    }
    if normalized in interface_only_values:
        return {
            "valid": False,
            "task_type": task_type,
            "reason": "Answer contained only interface boilerplate.",
        }

    return {
        "valid": True,
        "task_type": task_type,
        "reason": "Substantive narrative research answer",
        "cleaned_answer": cleaned,
    }


def snapshot_is_materializing(records):
    """Recognize transient dataset records returned while a snapshot builds."""
    if len(records) != 1 or not isinstance(records[0], dict):
        return False
    status = str(records[0].get("status", "")).strip().lower()
    return status in {
        "building", "collecting", "digesting", "running", "processing", "pending",
    }
