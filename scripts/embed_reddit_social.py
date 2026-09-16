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
runtime_cell["source"] = runtime_source.splitlines(keepends=True)

orchestration_cell = notebook["cells"][5]
source = "".join(orchestration_cell["source"])

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
new_visibility = '''    visibility_task = asyncio.create_task(
        run_visibility_stage(
            target_profile=target_profile,
            all_profiles=all_profiles,
            keywords=keywords,
        )
    )

    reddit_task = asyncio.create_task(
        run_reddit_social_stage(
            target_profile=target_profile,
            competitor_profiles=competitor_profiles,
            keywords=keywords,
            keyword_serp_results=keyword_serp_results,
            audit_focus=settings.get("audit_focus", ""),
        )
    )

    visibility_result, reddit_social_result = await asyncio.gather(
        visibility_task,
        reddit_task,
    )
'''
source = replace_or_verify(
    source,
    old_visibility,
    new_visibility,
    "parallel visibility tasks",
)

stage6_marker = '''    # --------------------------------------------------------
    # Stage 6: final report
    # --------------------------------------------------------
'''
reddit_output = '''    reddit_status = reddit_social_result.get("status", "failed")
    if reddit_status in {"success", "partial"}:
        print_stage_success(
            f"Reddit sample: {len(reddit_social_result.get('sample', []))} thread(s) "
            f"in {format_duration(reddit_social_result.get('duration_seconds', 0))}"
        )
    elif reddit_status != "disabled":
        warning = "Reddit conversation collection was unavailable"
        warnings.append(warning)
        print_stage_warning(warning)

    for reddit_warning in reddit_social_result.get("warnings", []):
        warnings.append(reddit_warning)

    write_json(
        output_directory / "05_reddit_social.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            **reddit_social_result,
        },
    )

'''
source = replace_or_verify(
    source,
    stage6_marker,
    reddit_output + stage6_marker,
    "Reddit stage output",
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
source = replace_or_verify(
    source,
    old_audit_data,
    new_audit_data,
    "Reddit structured output",
)

orchestration_cell["source"] = source.splitlines(keepends=True)
NOTEBOOK.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
