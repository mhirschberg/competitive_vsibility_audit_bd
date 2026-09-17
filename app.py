import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gradio as gr


APP_ROOT = Path(__file__).resolve().parent
NOTEBOOK_PATH = APP_ROOT / "competitive_visibility_audit_bd.ipynb"
CONFIG_CELL_ID = "UsMNZ4-2jKg6"
INSTALL_CELL_ID = "Y4uHcoSjjCGE"


def _configured_audit_concurrency():
    try:
        return max(1, int(os.getenv("AUDIT_CONCURRENCY", "1")))
    except ValueError:
        return 1


AUDIT_EXECUTOR = ThreadPoolExecutor(
    max_workers=_configured_audit_concurrency(),
    thread_name_prefix="competitive-audit",
)
AUDIT_JOBS = {}
AUDIT_JOBS_LOCK = threading.Lock()


def _cell_source(cell):
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return source


def _build_config_cell(
    company_name,
    company_domain,
    audit_focus,
    country,
    search_engine,
    include_reddit_analysis,
    debug_mode,
):
    values = {
        "company_name": str(company_name or "").strip(),
        "company_domain": str(company_domain or "").strip(),
        "audit_focus": str(audit_focus or "").strip(),
        "country": str(country or "US").strip().upper(),
        "search_engine": str(search_engine or "auto").strip().lower(),
        "include_reddit_analysis": bool(include_reddit_analysis),
        "debug_mode": bool(debug_mode),
    }
    payload = json.dumps(values, ensure_ascii=False)

    return f'''
import os
from urllib.parse import urlparse

_WEB_CONFIG = json.loads({json.dumps(payload)})

COMPANY_NAME = _WEB_CONFIG["company_name"]
COMPANY_DOMAIN = _WEB_CONFIG["company_domain"]
AUDIT_FOCUS = _WEB_CONFIG["audit_focus"]
COUNTRY = _WEB_CONFIG["country"]
SEARCH_ENGINE = _WEB_CONFIG["search_engine"]
AUTO_DOWNLOAD_REPORT = False
INCLUDE_REDDIT_ANALYSIS = bool(_WEB_CONFIG["include_reddit_analysis"])
DEBUG_MODE = bool(_WEB_CONFIG["debug_mode"])

BRIGHTDATA_API_TOKEN = os.getenv("BRIGHTDATA_API_TOKEN", "").strip()
SERP_ZONE = os.getenv("SERP_ZONE", "").strip()

if not BRIGHTDATA_API_TOKEN:
    raise ValueError("BRIGHTDATA_API_TOKEN is not configured on the server.")
if not SERP_ZONE:
    raise ValueError("SERP_ZONE is not configured on the server.")
if not COMPANY_NAME:
    raise ValueError("COMPANY_NAME cannot be empty.")
if not COMPANY_DOMAIN:
    raise ValueError("COMPANY_DOMAIN cannot be empty.")
if not COUNTRY:
    raise ValueError("COUNTRY cannot be empty.")
if SEARCH_ENGINE not in {{"auto", "google", "bing", "none"}}:
    raise ValueError("SEARCH_ENGINE must be auto, google, bing, or none.")

if not COMPANY_DOMAIN.lower().startswith(("http://", "https://")):
    COMPANY_URL = f"https://{{COMPANY_DOMAIN}}"
else:
    COMPANY_URL = COMPANY_DOMAIN

parsed_company_url = urlparse(COMPANY_URL)
if not parsed_company_url.hostname:
    raise ValueError(f"Invalid company domain or URL: {{COMPANY_DOMAIN}}")

COMPANY_HOSTNAME = parsed_company_url.hostname.lower().removeprefix("www.")
COMPANY_URL = f"{{parsed_company_url.scheme or 'https'}}://{{parsed_company_url.hostname}}/"

AUDIT_SETTINGS = {{
    "company_name": COMPANY_NAME,
    "company_url": COMPANY_URL,
    "company_domain": COMPANY_HOSTNAME,
    "audit_focus": AUDIT_FOCUS,
    "country": COUNTRY,
    "search_engine": SEARCH_ENGINE,
    "serp_zone": SERP_ZONE,
    "auto_download": False,
    "include_reddit_analysis": INCLUDE_REDDIT_ANALYSIS,
    "debug": DEBUG_MODE,
}}

print("✓ Audit configured")
print()
print(f"Company: {{COMPANY_NAME}}")
print(f"Website: {{COMPANY_URL}}")
print(f"Country: {{COUNTRY}}")
print(f"Audit focus: {{AUDIT_FOCUS or 'Primary offering'}}")
print(f"Search engine: {{SEARCH_ENGINE}}")
print(
    f"Reddit conversation analysis: "
    f"{{'enabled' if INCLUDE_REDDIT_ANALYSIS else 'skipped'}}"
)
print(f"Debug logging: {{'enabled' if DEBUG_MODE else 'disabled'}}")
'''


def _build_runner_script(
    company_name,
    company_domain,
    audit_focus,
    country,
    search_engine,
    include_reddit_analysis,
    debug_mode,
):
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    chunks = [
        "# Auto-generated workshop runner from the existing notebook.\n",
        "import json\n",
        "def display(value):\n    print(value)\n",
    ]

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue

        cell_id = cell.get("metadata", {}).get("id", "")
        if cell_id == INSTALL_CELL_ID:
            chunks.append('print("✓ Dependencies already installed")\n')
            continue
        if cell_id == CONFIG_CELL_ID:
            chunks.append(
                _build_config_cell(
                    company_name,
                    company_domain,
                    audit_focus,
                    country,
                    search_engine,
                    include_reddit_analysis,
                    debug_mode,
                )
            )
            continue

        source = _cell_source(cell)
        if not source.strip():
            continue

        source = re.sub(
            r"AUDIT_RESULT\s*=\s*await\s+run_competitive_visibility_audit\(\s*AUDIT_SETTINGS\s*\)",
            "AUDIT_RESULT = asyncio.run(run_competitive_visibility_audit(AUDIT_SETTINGS))",
            source,
            flags=re.MULTILINE,
        )
        # The notebook targets Colab's writable /content directory. Each web
        # run already has an isolated working directory, so keep its outputs
        # there when executing on Render (or any other host).
        source = source.replace('Path("/content")', "Path.cwd()")
        source = source.replace("Path('/content')", "Path.cwd()")
        chunks.append("\n# ---- notebook cell ----\n")
        chunks.append(source)
        if not source.endswith("\n"):
            chunks.append("\n")

    return "".join(chunks)


def _collect_downloads(run_dir: Path):
    preferred = []
    patterns = [
        "competitive-visibility-*.zip",
        "competitive-visibility-*/06_competitive_visibility_audit.pdf",
        "competitive-visibility-*/06_competitive_visibility_audit.md",
        "competitive-visibility-*/06_competitive_visibility_audit.json",
    ]
    for pattern in patterns:
        preferred.extend(sorted(run_dir.glob(pattern)))

    if preferred:
        return [str(path) for path in preferred if path.is_file()]

    fallback = [
        path
        for path in run_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".zip", ".pdf", ".md", ".json"}
    ]
    return [str(path) for path in sorted(fallback)]


def _validate_audit_request(company_name, company_domain):
    if not NOTEBOOK_PATH.exists():
        raise gr.Error(f"Notebook not found: {NOTEBOOK_PATH.name}")
    if not os.getenv("BRIGHTDATA_API_TOKEN", "").strip():
        raise gr.Error("Server secret BRIGHTDATA_API_TOKEN is missing.")
    if not os.getenv("SERP_ZONE", "").strip():
        raise gr.Error("Server secret SERP_ZONE is missing.")
    if not str(company_name or "").strip():
        raise gr.Error("Company name is required.")
    if not str(company_domain or "").strip():
        raise gr.Error("Company domain is required.")


def run_audit(
    company_name,
    company_domain,
    audit_focus,
    country,
    search_engine,
    include_reddit_analysis,
    debug_mode,
):
    _validate_audit_request(company_name, company_domain)

    run_dir = Path(tempfile.mkdtemp(prefix="competitive-audit-"))
    runner_path = run_dir / "workshop_runner.py"

    try:
        runner_path.write_text(
            _build_runner_script(
                company_name,
                company_domain,
                audit_focus,
                country,
                search_engine,
                include_reddit_analysis,
                debug_mode,
            ),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        process = subprocess.Popen(
            [sys.executable, "-u", str(runner_path)],
            cwd=run_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        lines = []
        yield "Starting audit…", []

        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line.rstrip("\n"))
            yield "\n".join(lines[-800:]), []

        return_code = process.wait()
        downloads = _collect_downloads(run_dir)

        if return_code != 0:
            lines.extend(["", f"✗ Audit failed (exit code {return_code})."])
            yield "\n".join(lines[-800:]), downloads
            return

        lines.extend(["", "✓ Audit completed"])
        if downloads:
            lines.append("✓ Report files are ready to download below.")
        else:
            lines.append("⚠ Audit completed, but no report files were found.")
        yield "\n".join(lines[-800:]), downloads

    except Exception as exc:
        yield f"Audit failed before completion:\n{type(exc).__name__}: {exc}", []


def _job_view(run_id):
    if not run_id:
        return "", []

    with AUDIT_JOBS_LOCK:
        job = AUDIT_JOBS.get(run_id)
        if job is None:
            return (
                "The previous audit is no longer available. "
                "It may have been cleared by a server restart.",
                [],
            )
        status = job["status"]
        logs = job["logs"]
        downloads = list(job["downloads"])

    if status == "queued" and not logs:
        logs = "Audit queued. It will start as soon as a worker is available…"
    return logs, downloads


def _execute_audit_job(run_id, arguments):
    with AUDIT_JOBS_LOCK:
        AUDIT_JOBS[run_id]["status"] = "running"

    latest_logs = "Starting audit…"
    latest_downloads = []
    try:
        for latest_logs, latest_downloads in run_audit(*arguments):
            with AUDIT_JOBS_LOCK:
                job = AUDIT_JOBS[run_id]
                job["logs"] = latest_logs
                job["downloads"] = list(latest_downloads)

        final_status = (
            "complete"
            if "✓ Audit completed" in latest_logs
            else "failed"
        )
    except Exception as exc:
        latest_logs = f"Audit failed before completion:\n{type(exc).__name__}: {exc}"
        latest_downloads = []
        final_status = "failed"

    with AUDIT_JOBS_LOCK:
        job = AUDIT_JOBS[run_id]
        job["status"] = final_status
        job["logs"] = latest_logs
        job["downloads"] = list(latest_downloads)


def start_audit_job(
    company_name,
    company_domain,
    audit_focus,
    country,
    search_engine,
    include_reddit_analysis,
    debug_mode,
    browser_state,
):
    _validate_audit_request(company_name, company_domain)

    saved_state = dict(browser_state or {})
    existing_run_id = saved_state.get("run_id")
    with AUDIT_JOBS_LOCK:
        existing_job = AUDIT_JOBS.get(existing_run_id)
        if existing_job and existing_job["status"] in {"queued", "running"}:
            raise gr.Error(
                "An audit is already running in this browser. "
                "Its progress will continue updating below."
            )

    arguments = (
        company_name,
        company_domain,
        audit_focus,
        country,
        search_engine,
        include_reddit_analysis,
        debug_mode,
    )
    run_id = uuid.uuid4().hex
    with AUDIT_JOBS_LOCK:
        AUDIT_JOBS[run_id] = {
            "status": "queued",
            "logs": "",
            "downloads": [],
        }

    AUDIT_EXECUTOR.submit(_execute_audit_job, run_id, arguments)

    saved_state.update(
        {
            "run_id": run_id,
            "company_name": str(company_name or ""),
            "company_domain": str(company_domain or ""),
            "audit_focus": str(audit_focus or ""),
            "country": str(country or "US"),
            "search_engine": str(search_engine or "auto"),
            "include_reddit_analysis": bool(include_reddit_analysis),
            "debug_mode": bool(debug_mode),
        }
    )
    logs, downloads = _job_view(run_id)
    return logs, downloads, saved_state


def poll_audit_job(browser_state):
    saved_state = browser_state or {}
    return _job_view(saved_state.get("run_id"))


def restore_audit_session(browser_state):
    saved_state = browser_state or {}
    logs, downloads = _job_view(saved_state.get("run_id"))
    return (
        saved_state.get("company_name", ""),
        saved_state.get("company_domain", ""),
        saved_state.get("audit_focus", ""),
        saved_state.get("country", "US"),
        saved_state.get("search_engine", "auto"),
        bool(saved_state.get("include_reddit_analysis", False)),
        bool(saved_state.get("debug_mode", False)),
        logs,
        downloads,
    )


def build_ui():
    with gr.Blocks(title="Competitive Visibility Audit") as demo:
        browser_state = gr.BrowserState(
            {},
            storage_key="competitive-visibility-audit-session",
            secret="competitive-visibility-audit-v1",
        )
        gr.Markdown(
            "# Competitive Visibility Audit\n"
            "Run a live competitive visibility audit using Bright Data."
        )

        with gr.Row():
            company_name = gr.Textbox(label="Company / brand", placeholder="Apple")
            company_domain = gr.Textbox(label="Official website", placeholder="apple.com")

        audit_focus = gr.Textbox(
            label="Audit focus (optional)",
            placeholder="e.g. iPhone, enterprise backup, facial moisturizer",
        )

        with gr.Row():
            country = gr.Textbox(label="Country code", value="US", max_lines=1)
            search_engine = gr.Dropdown(
                label="Traditional search engine",
                choices=["auto", "google", "bing", "none"],
                value="auto",
            )
            debug_mode = gr.Checkbox(label="Debug mode", value=False)

        include_reddit_analysis = gr.Checkbox(
            label="Include Reddit conversation analysis",
            value=False,
            info=(
                "Optional. May add up to 10 minutes and uses additional "
                "Bright Data dataset requests."
            ),
        )

        run_button = gr.Button("Run audit", variant="primary")
        logs = gr.Textbox(label="Live audit output", lines=24, interactive=False)
        downloads = gr.File(label="Download report files", file_count="multiple")
        refresh_timer = gr.Timer(value=5.0, active=True)

        run_button.click(
            fn=start_audit_job,
            inputs=[
                company_name,
                company_domain,
                audit_focus,
                country,
                search_engine,
                include_reddit_analysis,
                debug_mode,
                browser_state,
            ],
            outputs=[logs, downloads, browser_state],
            queue=False,
        )

        refresh_timer.tick(
            fn=poll_audit_job,
            inputs=[browser_state],
            outputs=[logs, downloads],
            queue=False,
            show_progress="hidden",
        )

        demo.load(
            fn=restore_audit_session,
            inputs=[browser_state],
            outputs=[
                company_name,
                company_domain,
                audit_focus,
                country,
                search_engine,
                include_reddit_analysis,
                debug_mode,
                logs,
                downloads,
            ],
            queue=False,
        )

    return demo


if __name__ == "__main__":
    username = os.getenv("APP_USERNAME", "").strip()
    password = os.getenv("APP_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("APP_USERNAME and APP_PASSWORD must be configured.")

    app = build_ui()
    app.queue(
        default_concurrency_limit=_configured_audit_concurrency(),
        max_size=100,
    )
    app.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        auth=(username, password),
        show_error=True,
    )
