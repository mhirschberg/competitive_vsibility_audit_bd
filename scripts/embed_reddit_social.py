"""Embed reddit_social.py and its orchestration hooks into the notebook."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "competitive_visibility_audit_bd.ipynb"
MODULE = ROOT / "reddit_social.py"
START = "# REDDIT-SOCIAL-PATCH: start"
END = "# REDDIT-SOCIAL-PATCH: end"


def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"Could not find notebook hook: {label}")
    if text.count(old) != 1:
        raise RuntimeError(f"Notebook hook is not unique: {label}")
    return text.replace(old, new, 1)


def replace_or_verify(text, old, new, label):
    if new in text:
        return text
    if old in text:
        return replace_once(text, old, new, label)
    raise RuntimeError(f"Could not find original or patched notebook hook: {label}")


notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
helper_cell = notebook["cells"][3]
helper_source = "".join(helper_cell["source"])
verbose_citation_log = '''    if (
        resolved_url
        and "bd_client" in globals()
        and bd_client.debug
    ):
        bd_client.log(
            f"Resolved Google citation: "
            f"{url[:70]}... -> "
            f"{resolved_url}"
        )

'''
helper_source = helper_source.replace(verbose_citation_log, "", 1)
helper_cell["source"] = helper_source.splitlines(keepends=True)

runtime_cell = notebook["cells"][6]
runtime_source = "".join(runtime_cell["source"])
embedded = MODULE.read_text(encoding="utf-8")
patch = f"\n\n{START}\n{embedded}\n{END}\n"

if START in runtime_source:
    before, remainder = runtime_source.split(START, 1)
    _, after = remainder.split(END, 1)
    runtime_source = before.rstrip() + patch + after.lstrip("\n")
else:
    runtime_source = runtime_source.rstrip() + patch

old_utility_snapshot_log = '''                bd_client.log(
                    f"{requests_by_engine[engine]['engine_name']} "
                    f"utility snapshot: {snapshot_id}"
                )
'''
new_utility_snapshot_log = '''                bd_client.log(
                    f"[{task_name}] "
                    f"{requests_by_engine[engine]['engine_name']} "
                    f"utility snapshot: {snapshot_id}"
                )
'''
runtime_source = replace_or_verify(
    runtime_source,
    old_utility_snapshot_log,
    new_utility_snapshot_log,
    "contextual utility snapshot log",
)

old_failure_engine = '''                "engine": result.get(
                    "engine_name"
                ),
                "status": result.get(
'''
new_failure_engine = '''                "engine": result.get(
                    "engine_name"
                ),
                "snapshot_id": result.get(
                    "snapshot_id"
                ),
                "status": result.get(
'''
runtime_source = replace_or_verify(
    runtime_source,
    old_failure_engine,
    new_failure_engine,
    "failed utility snapshot id",
)

runtime_source = runtime_source.replace(verbose_citation_log, "", 1)

old_weasy_import = '''    import html as html_module

    from markdown import markdown
    from weasyprint import HTML
'''
new_weasy_import = '''    import html as html_module
    import logging

    logging.getLogger("weasyprint").setLevel(logging.ERROR)
    from markdown import markdown
    from weasyprint import HTML
'''
runtime_source = replace_or_verify(
    runtime_source,
    old_weasy_import,
    new_weasy_import,
    "quiet PDF dependency warnings",
)
runtime_cell["source"] = runtime_source.splitlines(keepends=True)

orchestration_cell = notebook["cells"][5]
source = "".join(orchestration_cell["source"])
source = source.replace(verbose_citation_log, "", 1)

old_print_stage = '''def print_stage(
    stage_number,
    title,
):
    console.print(
        f"\\n[bold cyan]"
        f"[{stage_number}/6] "
        f"{title}"
        f"[/bold cyan]"
    )
'''
new_print_stage = '''def print_stage(
    stage_number,
    title,
    total_stages,
):
    console.print(
        f"\\n[bold cyan]"
        f"[{stage_number}/{total_stages}] "
        f"{title}"
        f"[/bold cyan]"
    )
'''
source = replace_or_verify(
    source,
    old_print_stage,
    new_print_stage,
    "dynamic progress stage count",
)

old_settings = '''    settings = dict(settings)

    audit_started_at = (
'''
new_settings = '''    settings = dict(settings)
    include_reddit_analysis = bool(
        settings.get(
            "include_reddit_analysis",
            False,
        )
    )
    total_stages = 7 if include_reddit_analysis else 6

    audit_started_at = (
'''
source = replace_or_verify(
    source,
    old_settings,
    new_settings,
    "dynamic audit stage setup",
)

old_stage_docs = '''    5. ChatGPT and Gemini visibility
    6. Final report and export
'''
new_stage_docs = '''    5. ChatGPT and Gemini visibility
    6. Optional Reddit conversation analysis
    7. Final report and export when Reddit is enabled; otherwise Stage 6
'''
source = replace_or_verify(
    source,
    old_stage_docs,
    new_stage_docs,
    "documented optional social stage",
)

stage_titles = {
    1: "Company analysis and buyer keywords",
    2: "Web Search and AI Mode competitor discovery",
    3: "Direct competitor selection",
    4: "Target and competitor profiles",
    5: "Cross-engine AI visibility",
}
for stage_number, title in stage_titles.items():
    old_call = f'''    print_stage(
        {stage_number},
        "{title}",
    )
'''
    new_call = f'''    print_stage(
        {stage_number},
        "{title}",
        total_stages,
    )
'''
    source = replace_or_verify(
        source,
        old_call,
        new_call,
        f"stage {stage_number} total",
    )

stage4_marker = '''    # --------------------------------------------------------
    # Stage 4: profiles
    # --------------------------------------------------------
'''
prefetch_before_stage4 = '''    reddit_prefetch_task = None
    if include_reddit_analysis:
        console.print(
            "      [cyan]↗ Social discovery started in parallel; "
            "snapshots are labelled [Social · …].[/cyan]"
        )
        reddit_prefetch_task = asyncio.create_task(
            start_reddit_discovery_prefetch(
                target_brand=target_brand,
                selected_competitors=selected_competitors,
                keywords=keywords,
                audit_focus=settings.get("audit_focus", ""),
            )
        )

''' + stage4_marker
previous_prefetch_before_stage4 = '''    include_reddit_analysis = bool(
        settings.get(
            "include_reddit_analysis",
            False,
        )
    )
    reddit_prefetch_task = None
    if include_reddit_analysis:
        reddit_prefetch_task = asyncio.create_task(
            start_reddit_discovery_prefetch(
                target_brand=target_brand,
                selected_competitors=selected_competitors,
                keywords=keywords,
                audit_focus=settings.get("audit_focus", ""),
            )
        )

''' + stage4_marker
if previous_prefetch_before_stage4 in source:
    source = source.replace(
        previous_prefetch_before_stage4,
        prefetch_before_stage4,
        1,
    )
source = replace_or_verify(
    source,
    stage4_marker,
    prefetch_before_stage4,
    "early Reddit discovery prefetch",
)

old_visibility = '''    visibility_result = (
        await run_visibility_stage(
            target_profile=(
                target_profile
            ),
            all_profiles=all_profiles,
            keywords=keywords,
        )
    )
'''
previous_parallel_visibility = '''    visibility_task = asyncio.create_task(
        run_visibility_stage(
            target_profile=target_profile,
            all_profiles=all_profiles,
            keywords=keywords,
        )
    )

    if include_reddit_analysis:
        reddit_task = asyncio.create_task(
            run_reddit_social_stage(
                target_profile=target_profile,
                competitor_profiles=competitor_profiles,
                keywords=keywords,
                keyword_serp_results=keyword_serp_results,
                audit_focus=settings.get("audit_focus", ""),
                discovery_prefetch_task=reddit_prefetch_task,
            )
        )
        visibility_result, reddit_social_result = await asyncio.gather(
            visibility_task,
            reddit_task,
        )
    else:
        visibility_result = await visibility_task
        reddit_social_result = {
            "status": "disabled",
            "mode": "disabled",
            "queries": [],
            "sample": [],
            "metrics": {},
            "cohorts": [],
            "comparison": [],
            "warnings": [],
            "duration_seconds": 0.0,
        }
'''
previous_visibility = previous_parallel_visibility.replace(
    '            discovery_prefetch_task=reddit_prefetch_task,\n',
    '',
)
if previous_visibility in source:
    source = source.replace(previous_visibility, previous_parallel_visibility, 1)
new_visibility = previous_parallel_visibility.replace(
    '''        visibility_result, reddit_social_result = await asyncio.gather(
            visibility_task,
            reddit_task,
        )
''',
    '''        visibility_result = await visibility_task
''',
)
if previous_parallel_visibility in source:
    source = source.replace(previous_parallel_visibility, new_visibility, 1)
source = replace_or_verify(
    source,
    old_visibility,
    new_visibility,
    "parallel visibility tasks",
)

stage6_marker = '''    # --------------------------------------------------------
    # Final stage: final report
    # --------------------------------------------------------
'''
old_stage6_marker = '''    # --------------------------------------------------------
    # Stage 6: final report
    # --------------------------------------------------------
'''
if old_stage6_marker in source:
    source = source.replace(old_stage6_marker, stage6_marker, 1)
reddit_output = '''    if include_reddit_analysis:
        print_stage(
            6,
            "Reddit conversation analysis",
            total_stages,
        )
        reddit_social_result = await reddit_task
        stage_durations["reddit_social"] = float(
            reddit_social_result.get("duration_seconds") or 0
        )
    else:
        stage_durations["reddit_social"] = 0.0

    reddit_status = reddit_social_result.get("status", "failed")
    if reddit_status in {"success", "partial"}:
        if reddit_social_result.get("mode") == "competitive":
            comparison = reddit_social_result.get("comparison", [])
            cohort_summary = ", ".join(
                f"{item.get('brand')}: {item.get('relevant_posts', 0)} relevant / "
                f"{item.get('classified_posts', 0)} classified / "
                f"{item.get('sample_size', 0)} sampled"
                for item in comparison
            )
            print_stage_success(
                f"Reddit competitive sample: {cohort_summary}; "
                f"{reddit_social_result.get('unique_thread_count', 0)} unique thread(s) "
                f"in {format_duration(reddit_social_result.get('duration_seconds', 0))}"
            )
        else:
            print_stage_success(
                f"Reddit sample: {len(reddit_social_result.get('sample', []))} thread(s) "
                f"in {format_duration(reddit_social_result.get('duration_seconds', 0))}"
            )
    reddit_summary_warning = summarize_reddit_audit_warning(
        reddit_social_result
    )
    if reddit_summary_warning:
        warnings.append(reddit_summary_warning)
        print_stage_warning(reddit_summary_warning)

    write_json(
        output_directory / "05_reddit_social.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            **reddit_social_result,
        },
    )

    write_json(
        output_directory / "05_reddit_snapshot_manifest.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "snapshots": reddit_social_result.get("snapshot_manifest", []),
        },
    )

'''
reddit_output_start = '    reddit_status = reddit_social_result.get("status", "failed")\n'
reddit_output_start_new = '''    if include_reddit_analysis:
        print_stage(
            6,
            "Reddit conversation analysis",
            total_stages,
        )
'''
active_reddit_output_start = (
    reddit_output_start_new
    if reddit_output_start_new in source
    else reddit_output_start
)
if active_reddit_output_start in source:
    before, remainder = source.split(active_reddit_output_start, 1)
    if stage6_marker not in remainder:
        raise RuntimeError("Could not find Stage 6 after Reddit stage output")
    _, after = remainder.split(stage6_marker, 1)
    source = before + reddit_output + stage6_marker + after
else:
    source = replace_once(
        source,
        stage6_marker,
        reddit_output + stage6_marker,
        "Reddit stage output",
    )

old_final_stage = '''    print_stage(
        6,
        "Final report and export",
    )
'''
new_final_stage = '''    print_stage(
        7 if include_reddit_analysis else 6,
        "Final report and export",
        total_stages,
    )
'''
source = replace_or_verify(
    source,
    old_final_stage,
    new_final_stage,
    "dynamic final report stage",
)

old_final_report = '''    final_report = (
        finalized_report["report"]
    )
'''
new_final_report = old_final_report + '''
    final_report = insert_reddit_report_section(
        final_report,
        reddit_social_result,
    )
'''
source = replace_or_verify(
    source,
    old_final_report,
    new_final_report,
    "Reddit report section",
)

old_audit_data = '''        "final_report": {
'''
new_audit_data = '''        "reddit_social": reddit_social_result,
        "final_report": {
'''
reddit_audit_field = '        "reddit_social": reddit_social_result,\n'
if reddit_audit_field not in source:
    source = replace_or_verify(
        source,
        old_audit_data,
        new_audit_data,
        "Reddit structured output",
    )
elif source.count(reddit_audit_field) != 1:
    raise RuntimeError("Reddit structured output must appear exactly once")

orchestration_cell["source"] = source.splitlines(keepends=True)
NOTEBOOK.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
