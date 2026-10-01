"""Audit checkpoint and report file writers shared by service and notebook."""

import json
from pathlib import Path
import zipfile

# SERVICE-ONLY-IMPORTS: start
from .artifact_names import is_final_report_json
# SERVICE-ONLY-IMPORTS: end


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False, default=str)
    return path


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(str(text or ""))
    return path


def create_audit_zip(output_directory, archive_name=None):
    output_directory = Path(output_directory)
    if archive_name is not None and Path(archive_name).name != archive_name:
        raise ValueError("Archive name must be a filename, not a path")
    zip_path = output_directory.parent / (
        archive_name or f"{output_directory.name}.zip"
    )
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in output_directory.rglob("*"):
            if not path.is_file():
                continue
            archive.write(path, arcname=path.relative_to(output_directory))
    return zip_path


def write_json_with_scope(
    path, data, *, locked_target_scope=None, market_category_override="",
    write_json_fn=write_json,
):
    """Preserve the notebook's locked-scope augmentation before writing."""
    path_object = Path(path)
    if locked_target_scope and isinstance(data, dict):
        if path_object.name in {
            "01_company_analysis.json", "03_competitor_selection.json",
        }:
            data["locked_target_scope"] = dict(locked_target_scope)
        elif is_final_report_json(path_object.name):
            data["locked_target_scope"] = dict(locked_target_scope)
            configuration = data.get("configuration")
            if isinstance(configuration, dict):
                configuration["market_category_override"] = market_category_override
    return write_json_fn(path, data)
