"""Deterministically embed shared Python sources into the standalone notebook.

Only tagged cells are generated for now. Other notebook cells remain untouched
until their logic has been extracted into service modules.
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "competitive_visibility_audit_bd.ipynb"
REDDIT_SOURCE = ROOT / "reddit_social.py"
RESEARCH_SOURCE = ROOT / "research_fallback.py"
PRIMITIVES_SOURCE = ROOT / "audit_core" / "primitives.py"
SCOPE_SOURCE = ROOT / "audit_core" / "competitor_scope.py"
COMPETITOR_RESEARCH_SOURCE = ROOT / "audit_core" / "competitor_research.py"
COMPETITOR_DECISIONS_SOURCE = ROOT / "audit_core" / "competitor_decisions.py"
COMPETITOR_PIPELINE_SOURCE = ROOT / "audit_core" / "competitor_pipeline.py"
COMPETITOR_STAGE_SOURCE = ROOT / "audit_core" / "competitor_stage.py"
PRIMITIVES_CELL_ID = "final-core"
PRIMITIVES_START = "# AUDIT-PRIMITIVES: start"
PRIMITIVES_END = "# AUDIT-PRIMITIVES: end"
SCOPE_CELL_ID = "runtime-utilities-merged"
SCOPE_START = "# AUDIT-COMPETITOR-SCOPE: start"
SCOPE_END = "# AUDIT-COMPETITOR-SCOPE: end"
SCOPE_PACKAGE_IMPORT = "from .primitives import normalize_confidence\n"
COMPETITOR_RESEARCH_START = "# AUDIT-COMPETITOR-RESEARCH: start"
COMPETITOR_RESEARCH_END = "# AUDIT-COMPETITOR-RESEARCH: end"
COMPETITOR_DECISIONS_START = "# AUDIT-COMPETITOR-DECISIONS: start"
COMPETITOR_DECISIONS_END = "# AUDIT-COMPETITOR-DECISIONS: end"
COMPETITOR_PIPELINE_START = "# AUDIT-COMPETITOR-PIPELINE: start"
COMPETITOR_PIPELINE_END = "# AUDIT-COMPETITOR-PIPELINE: end"
COMPETITOR_STAGE_START = "# AUDIT-COMPETITOR-STAGE: start"
COMPETITOR_STAGE_END = "# AUDIT-COMPETITOR-STAGE: end"
SERVICE_IMPORTS_START = "# SERVICE-ONLY-IMPORTS: start"
SERVICE_IMPORTS_END = "# SERVICE-ONLY-IMPORTS: end"
REDDIT_CELL_ID = "runtime-utilities-merged"
RESEARCH_CELL_ID = "research-provider-race"
REDDIT_START = "# REDDIT-SOCIAL-PATCH: start"
REDDIT_END = "# REDDIT-SOCIAL-PATCH: end"
RESEARCH_HEADER = (
    "#@title 3E. Load resilient research providers\n"
    "#@markdown Race ChatGPT and Gemini for internal research; "
    "keep Google AI Mode measured separately.\n\n"
)


def _unique_cell(notebook, cell_id):
    matches = [
        cell for cell in notebook["cells"]
        if cell.get("metadata", {}).get("id") == cell_id
    ]
    if len(matches) != 1 or matches[0].get("cell_type") != "code":
        raise ValueError(f"Expected exactly one code cell with id {cell_id!r}")
    return matches[0]


def _replace_embedded_source(cell, start, end, source):
    text = "".join(cell["source"])
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"Expected exactly one {start!r}/{end!r} marker pair")
    prefix, remainder = text.split(start, 1)
    _, suffix = remainder.split(end, 1)
    if start in suffix or end in prefix:
        raise ValueError("Embedded source markers are out of order")
    cell["source"] = (
        prefix + start + "\n" + source.rstrip("\n") + "\n" + end + suffix
    ).splitlines(keepends=True)


def _without_service_imports(source):
    if (source.count(SERVICE_IMPORTS_START) != 1
            or source.count(SERVICE_IMPORTS_END) != 1):
        raise ValueError("Expected one service-only import block")
    before, remainder = source.split(SERVICE_IMPORTS_START, 1)
    _, after = remainder.split(SERVICE_IMPORTS_END, 1)
    return before.rstrip("\n") + "\n\n" + after.lstrip("\n")


def build_notebook(notebook_path=NOTEBOOK, reddit_source=REDDIT_SOURCE,
                   research_source=RESEARCH_SOURCE,
                   primitives_source=PRIMITIVES_SOURCE,
                   scope_source=SCOPE_SOURCE,
                   competitor_research_source=COMPETITOR_RESEARCH_SOURCE,
                   competitor_decisions_source=COMPETITOR_DECISIONS_SOURCE,
                   competitor_pipeline_source=COMPETITOR_PIPELINE_SOURCE,
                   competitor_stage_source=COMPETITOR_STAGE_SOURCE):
    """Return notebook bytes with generated cells synchronized to sources."""
    notebook = json.loads(Path(notebook_path).read_text(encoding="utf-8"))
    primitives_cell = _unique_cell(notebook, PRIMITIVES_CELL_ID)
    _replace_embedded_source(
        primitives_cell,
        PRIMITIVES_START,
        PRIMITIVES_END,
        Path(primitives_source).read_text(encoding="utf-8"),
    )
    scope_text = Path(scope_source).read_text(encoding="utf-8")
    if scope_text.count(SCOPE_PACKAGE_IMPORT) != 1:
        raise ValueError("Expected one service-only primitives import")
    scope_text = scope_text.replace(SCOPE_PACKAGE_IMPORT, "", 1)
    scope_cell = _unique_cell(notebook, SCOPE_CELL_ID)
    _replace_embedded_source(
        scope_cell,
        SCOPE_START,
        SCOPE_END,
        scope_text,
    )
    _replace_embedded_source(
        scope_cell,
        COMPETITOR_RESEARCH_START,
        COMPETITOR_RESEARCH_END,
        Path(competitor_research_source).read_text(encoding="utf-8"),
    )
    decisions_text = _without_service_imports(
        Path(competitor_decisions_source).read_text(encoding="utf-8")
    )
    _replace_embedded_source(
        scope_cell,
        COMPETITOR_DECISIONS_START,
        COMPETITOR_DECISIONS_END,
        decisions_text,
    )
    _replace_embedded_source(
        scope_cell,
        COMPETITOR_PIPELINE_START,
        COMPETITOR_PIPELINE_END,
        _without_service_imports(
            Path(competitor_pipeline_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        scope_cell,
        COMPETITOR_STAGE_START,
        COMPETITOR_STAGE_END,
        _without_service_imports(
            Path(competitor_stage_source).read_text(encoding="utf-8")
        ),
    )
    reddit_cell = _unique_cell(notebook, REDDIT_CELL_ID)
    _replace_embedded_source(
        reddit_cell,
        REDDIT_START,
        REDDIT_END,
        Path(reddit_source).read_text(encoding="utf-8"),
    )
    research_cell = _unique_cell(notebook, RESEARCH_CELL_ID)
    research_cell["source"] = (
        RESEARCH_HEADER + Path(research_source).read_text(encoding="utf-8")
    ).splitlines(keepends=True)
    return (json.dumps(notebook, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
