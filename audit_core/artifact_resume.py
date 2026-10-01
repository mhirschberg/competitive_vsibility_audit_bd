"""Locate an incomplete audit or restore its saved checkpoint archive."""

import json
from pathlib import Path
import zipfile


def find_latest_audit_to_continue(settings, base_directory="/content"):
    expected_domain = str(settings["company_domain"]).lower()
    comparable = (
        "company_domain", "audit_focus", "country", "search_engine",
        "serp_zone", "include_reddit_analysis",
    )

    def settings_match(previous):
        return (
            all(previous.get(key) == settings.get(key) for key in comparable)
            and previous.get("reddit_comment_posts_per_cohort", 0)
            == settings.get("reddit_comment_posts_per_cohort", 0)
        )

    matches = []
    for directory in Path(base_directory).glob("competitive-visibility-*"):
        company_file = directory / "01_company_analysis.json"
        serp_file = directory / "02_serp_results.json"
        if not company_file.is_file() or not serp_file.is_file():
            continue
        if any(directory.glob("*_competitive_visibility_audit.json")):
            continue
        company_data = json.loads(company_file.read_text(encoding="utf-8"))
        actual_domain = str(company_data["brand"]["domain"]).lower()
        if actual_domain != expected_domain:
            continue
        settings_file = directory / "00_run_settings.json"
        if settings_file.exists():
            previous = json.loads(settings_file.read_text(encoding="utf-8"))
            if not settings_match(previous):
                continue
        matches.append(directory)

    if not matches:
        archives = sorted(
            {*Path(base_directory).glob("competitive-visibility-*.zip"),
             *Path(base_directory).glob("*_competitive_visibility_audit.zip")},
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for archive_path in archives:
            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
                if not {
                    "01_company_analysis.json", "02_serp_results.json",
                }.issubset(names):
                    continue
                previous_company = json.loads(
                    archive.read("01_company_analysis.json")
                )
                if str(previous_company["brand"]["domain"]).lower() != expected_domain:
                    continue
                if any(
                    name.endswith("_competitive_visibility_audit.json")
                    for name in names
                ):
                    continue
                if "00_run_settings.json" in names:
                    previous_settings = json.loads(
                        archive.read("00_run_settings.json")
                    )
                    if not settings_match(previous_settings):
                        continue
                if any(
                    Path(name).is_absolute() or ".." in Path(name).parts
                    for name in names
                ):
                    raise ValueError("Recovery ZIP contains unsafe paths.")
                restored_name = archive_path.stem
                if not restored_name.startswith("competitive-visibility-"):
                    restored_name = "competitive-visibility-" + restored_name
                restored = Path(base_directory) / restored_name
                if restored.exists():
                    continue
                restored.mkdir()
                archive.extractall(restored)
                matches.append(restored)
                break

    if not matches:
        raise FileNotFoundError(
            "No incomplete audit with saved steps 1–2 matches this "
            "company and configuration in /content. Do not start a "
            "new paid audit until its checkpoint is available."
        )
    return max(matches, key=lambda path: path.stat().st_mtime)
