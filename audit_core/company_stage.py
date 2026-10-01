"""Stage 1: load or analyze a company and persist its buyer-keyword checkpoint.

The provider request, model classes, state synchronization, and filesystem
writer are supplied by the caller. This makes the stage runnable without a
notebook, Colab globals, or the hosted web application.
"""

import asyncio
import json
import time


class CompanyStagePorts:
    def __init__(
        self, *, analyze, intake_factory, brand_factory, keyword_factory,
        get_locked_scope, set_locked_scope, restore_locked_scope,
        model_to_dict, write_json, clean_record, stage_success,
    ):
        self.analyze = analyze
        self.intake_factory = intake_factory
        self.brand_factory = brand_factory
        self.keyword_factory = keyword_factory
        self.get_locked_scope = get_locked_scope
        self.set_locked_scope = set_locked_scope
        self.restore_locked_scope = restore_locked_scope
        self.model_to_dict = model_to_dict
        self.write_json = write_json
        self.clean_record = clean_record
        self.stage_success = stage_success


async def run_company_stage_core(
    settings, *, continuing, output_directory, raw_directory,
    run_timestamp, started_at, ports,
):
    """Return the target and keywords while preserving checkpoint semantics."""
    if continuing:
        company_checkpoint = json.loads((
            output_directory / "01_company_analysis.json"
        ).read_text(encoding="utf-8"))
        company_result = {
            "intake": ports.intake_factory(
                brand=ports.brand_factory(**company_checkpoint["brand"]),
                buyer_intent_keywords=[
                    ports.keyword_factory(**item)
                    for item in company_checkpoint["buyer_intent_keywords"]
                ],
            ),
            "record": {},
        }
        existing_record = raw_directory / "01_company_ai_record.json"
        if existing_record.exists():
            company_result["record"] = json.loads(
                existing_record.read_text(encoding="utf-8")
            )
    else:
        company_result = await asyncio.to_thread(ports.analyze, settings)

    company_intake = company_result["intake"]
    target_brand = company_intake.brand
    target_brand.domain = settings["company_domain"]
    target_brand.official_url = settings["company_url"]

    # Prefer an explicit result from the company analyzer. The callback is a
    # compatibility path for older notebook analyzers that still publish the
    # scope through their shared runtime namespace.
    locked_scope = company_result.get("locked_target_scope")
    if not locked_scope:
        locked_scope = ports.get_locked_scope()
    if isinstance(locked_scope, dict):
        locked_scope = dict(locked_scope)
    if locked_scope:
        locked_scope["domain"] = target_brand.domain
        locked_scope["official_url"] = target_brand.official_url
    if continuing:
        locked_scope = ports.restore_locked_scope(
            company_checkpoint, target_brand, settings
        )
    # Notebook checkpoint writers and later report helpers still consume this
    # callback; the service pipeline also returns and passes the value directly.
    if locked_scope:
        ports.set_locked_scope(locked_scope)

    keyword_records = company_intake.buyer_intent_keywords
    keywords = [item.keyword for item in keyword_records]
    duration_seconds = (
        company_checkpoint.get("duration_seconds", 0.0)
        if continuing else time.monotonic() - started_at
    )
    ports.stage_success(
        f"{target_brand.brand_name} analyzed; "
        f"{len(keywords)} buyer keywords generated"
    )
    ports.write_json(output_directory / "01_company_analysis.json", {
        "created_at": run_timestamp.isoformat(),
        "brand": ports.model_to_dict(target_brand),
        "buyer_intent_keywords": [
            ports.model_to_dict(item) for item in keyword_records
        ],
        "duration_seconds": round(duration_seconds, 2),
    })
    ports.write_json(
        raw_directory / "01_company_ai_record.json",
        ports.clean_record(company_result["record"]),
    )
    if isinstance(company_result.get("structuring_record"), dict):
        ports.write_json(
            raw_directory / "01_company_structuring_record.json",
            ports.clean_record(company_result["structuring_record"]),
        )
    keyword_completion = company_result.get("keyword_completion")
    if (
        isinstance(keyword_completion, dict)
        and isinstance(keyword_completion.get("record"), dict)
    ):
        ports.write_json(
            raw_directory / "01_keyword_completion_record.json",
            ports.clean_record(keyword_completion["record"]),
        )
    return {
        "target_brand": target_brand,
        "keyword_records": keyword_records,
        "keywords": keywords,
        "duration_seconds": duration_seconds,
        "locked_scope": locked_scope,
    }
