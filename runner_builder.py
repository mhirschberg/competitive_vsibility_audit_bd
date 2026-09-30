"""Build the transitional standalone runner without importing the web UI."""

import json
import re
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
NOTEBOOK_PATH = APP_ROOT / "competitive_visibility_audit_bd.ipynb"
CONFIG_CELL_ID = "UsMNZ4-2jKg6"
INSTALL_CELL_ID = "Y4uHcoSjjCGE"


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
    wait_longer_for_google_ai_mode=False,
    include_copilot_visibility=True,
    reddit_comment_posts_per_cohort=0,
    include_google_ai_mode=False,
    include_chatgpt_visibility=True,
    wait_longer_for_chatgpt=False,
    include_gemini_visibility=True,
    wait_longer_for_gemini=False,
    wait_longer_for_copilot=False,
):
    reddit_comment_posts_per_cohort = int(reddit_comment_posts_per_cohort)
    if not 0 <= reddit_comment_posts_per_cohort <= 10:
        raise ValueError("Reddit comment posts per group must be between 0 and 10.")
    values = {
        "company_name": str(company_name or "").strip(),
        "company_domain": str(company_domain or "").strip(),
        "audit_focus": str(audit_focus or "").strip(),
        "country": str(country or "US").strip().upper(),
        "search_engine": str(search_engine or "auto").strip().lower(),
        "include_reddit_analysis": bool(include_reddit_analysis),
        "debug_mode": bool(debug_mode),
        "wait_longer_for_google_ai_mode": bool(wait_longer_for_google_ai_mode),
        "include_google_ai_mode": bool(include_google_ai_mode),
        "include_chatgpt_visibility": bool(include_chatgpt_visibility),
        "wait_longer_for_chatgpt": bool(wait_longer_for_chatgpt),
        "include_gemini_visibility": bool(include_gemini_visibility),
        "wait_longer_for_gemini": bool(wait_longer_for_gemini),
        "include_copilot_visibility": bool(include_copilot_visibility),
        "wait_longer_for_copilot": bool(wait_longer_for_copilot),
        "reddit_comment_posts_per_cohort": reddit_comment_posts_per_cohort,
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
REDDIT_COMMENT_POSTS_PER_COHORT = int(_WEB_CONFIG["reddit_comment_posts_per_cohort"])
os.environ["REDDIT_COMMENT_POSTS_PER_COHORT"] = str(REDDIT_COMMENT_POSTS_PER_COHORT)
INCLUDE_COPILOT_VISIBILITY = bool(_WEB_CONFIG["include_copilot_visibility"])
INCLUDE_GOOGLE_AI_MODE = bool(_WEB_CONFIG["include_google_ai_mode"])
INCLUDE_CHATGPT_VISIBILITY = bool(_WEB_CONFIG["include_chatgpt_visibility"])
INCLUDE_GEMINI_VISIBILITY = bool(_WEB_CONFIG["include_gemini_visibility"])
DEBUG_MODE = bool(_WEB_CONFIG["debug_mode"])
WAIT_LONGER_FOR_GOOGLE_AI_MODE = bool(_WEB_CONFIG["wait_longer_for_google_ai_mode"])
WAIT_LONGER_FOR_CHATGPT = bool(_WEB_CONFIG["wait_longer_for_chatgpt"])
WAIT_LONGER_FOR_GEMINI = bool(_WEB_CONFIG["wait_longer_for_gemini"])
WAIT_LONGER_FOR_COPILOT = bool(_WEB_CONFIG["wait_longer_for_copilot"])

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
    "reddit_comment_posts_per_cohort": REDDIT_COMMENT_POSTS_PER_COHORT,
    "include_copilot_visibility": INCLUDE_COPILOT_VISIBILITY,
    "include_google_ai_mode": INCLUDE_GOOGLE_AI_MODE,
    "wait_longer_for_google_ai_mode": WAIT_LONGER_FOR_GOOGLE_AI_MODE,
    "include_chatgpt_visibility": INCLUDE_CHATGPT_VISIBILITY,
    "include_gemini_visibility": INCLUDE_GEMINI_VISIBILITY,
    "wait_longer_for_chatgpt": WAIT_LONGER_FOR_CHATGPT,
    "wait_longer_for_gemini": WAIT_LONGER_FOR_GEMINI,
    "wait_longer_for_copilot": WAIT_LONGER_FOR_COPILOT,
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
if INCLUDE_REDDIT_ANALYSIS:
    print(f"Reddit comment collection: {{REDDIT_COMMENT_POSTS_PER_COHORT}} post(s) per group")
print(
    f"Copilot AI visibility: "
    f"{{'enabled' if INCLUDE_COPILOT_VISIBILITY else 'skipped'}}"
)
print("AI answer sources: " + ", ".join(
    name for name, enabled in (
        ("Google AI Mode", INCLUDE_GOOGLE_AI_MODE),
        ("ChatGPT", INCLUDE_CHATGPT_VISIBILITY),
        ("Gemini", INCLUDE_GEMINI_VISIBILITY),
        ("Copilot", INCLUDE_COPILOT_VISIBILITY),
    ) if enabled
))
print(f"Debug logging: {{'enabled' if DEBUG_MODE else 'disabled'}}")
if INCLUDE_GOOGLE_AI_MODE:
    print(f"Google AI Mode wait: {{'extended' if WAIT_LONGER_FOR_GOOGLE_AI_MODE else 'standard'}}")
'''


def _build_runner_script(
    company_name,
    company_domain,
    audit_focus,
    country,
    search_engine,
    include_reddit_analysis,
    debug_mode,
    wait_longer_for_google_ai_mode=False,
    include_copilot_visibility=True,
    reddit_comment_posts_per_cohort=0,
    include_google_ai_mode=False,
    include_chatgpt_visibility=True,
    wait_longer_for_chatgpt=False,
    include_gemini_visibility=True,
    wait_longer_for_gemini=False,
    wait_longer_for_copilot=False,
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
                    wait_longer_for_google_ai_mode,
                    include_copilot_visibility,
                    reddit_comment_posts_per_cohort,
                    include_google_ai_mode,
                    include_chatgpt_visibility,
                    wait_longer_for_chatgpt,
                    include_gemini_visibility,
                    wait_longer_for_gemini,
                    wait_longer_for_copilot,
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
