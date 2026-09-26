"""One Cloud Run Job execution runs one pinned notebook audit."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from uuid import UUID

from hosted.supabase_gateway import BackendError, SupabaseGateway
from scripts.run_local_audit import collect_artifacts


STAGE_LINE = re.compile(r"^\[\d+/\d+\]\s+(.+)$")


def _step_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:80] or "stage"


def _artifact_kind(path: Path) -> str:
    if path.name == "audit.log":
        return "log"
    if path.suffix == ".zip":
        return "zip_archive"
    if path.suffix == ".pdf":
        return "pdf_report"
    if path.suffix == ".md":
        return "markdown_report"
    if path.name == "06_competitive_visibility_audit.json":
        return "json_report"
    if path.name == "05_reddit_social.json":
        return "reddit_social"
    return "raw_json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _report_summary(report: dict) -> dict:
    target = report.get("target") or {}
    selected = (report.get("competitor_selection") or {}).get("selected") or []
    competitors = []
    for item in selected:
        if isinstance(item, dict):
            competitors.append(
                {
                    "name": item.get("brand_name") or item.get("name"),
                    "domain": item.get("domain"),
                }
            )
    return {
        "target_name": target.get("brand_name"),
        "competitors": competitors[:5],
        "warnings_count": len(report.get("warnings") or []),
        "completed_at": report.get("completed_at"),
    }


def _usage_rows(
    audit_id: UUID, execution_id: UUID, usage: dict
) -> list[dict]:
    price = usage.get("price_per_1000_results_usd")
    rows = []
    for event in usage.get("events") or []:
        operation_id = event.get("operation_id")
        if not isinstance(operation_id, int) or operation_id <= 0:
            continue
        status = str(event.get("status") or "started")
        result_count = event.get("result_count")
        expected_count = event.get("expected_result_count")
        accepted = (
            True if status in {"triggered", "success"}
            else False if status in {"failed", "error"}
            else None
        )
        estimated_count = (
            result_count if result_count is not None
            else expected_count if accepted else None
        )
        rows.append(
            {
                "audit_id": str(audit_id),
                "execution_id": str(execution_id),
                "source_operation_id": operation_id,
                "operation_name": str(event.get("operation") or "Bright Data operation"),
                "dataset_id": event.get("dataset_id") or None,
                "snapshot_id": event.get("snapshot_id") or None,
                "operation_status": status,
                "accepted": accepted,
                "input_count": int(event.get("input_count") or 0),
                "expected_result_count": expected_count,
                "confirmed_result_count": result_count,
                "unit_price_usd_per_1000": price,
                "estimated_cost_usd": (
                    round(float(estimated_count) * float(price) / 1000, 6)
                    if estimated_count is not None and price is not None
                    else None
                ),
                "estimate_is_lower_bound": result_count is None and accepted is not False,
            }
        )
    return rows


def _publish_artifact(gateway, audit: dict, audit_id: UUID, path: Path):
    workspace_id = audit["workspace_id"]
    object_path = f"workspaces/{workspace_id}/audits/{audit_id}/{path.name}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    gateway.upload_artifact(object_path, path, content_type)
    gateway.record_artifact(
        {
            "audit_id": str(audit_id),
            "kind": _artifact_kind(path),
            "bucket_id": "audit-artifacts",
            "object_path": object_path,
            "content_type": content_type,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    )


def run_worker(
    gateway,
    audit_id: UUID,
    *,
    runner_source_factory=None,
    python_executable=sys.executable,
    heartbeat_interval=30,
    platform_execution_id=None,
) -> int:
    """Return 0 on success/already-claimed, 1 on a recorded audit failure."""
    claim = gateway.claim_audit(audit_id, platform_execution_id)
    if claim is None:
        print("Audit already claimed or finished; no paid work started")
        return 0
    execution_id, claim_token = claim
    try:
        audit = gateway.get_audit(audit_id)
        options = audit.get("input_options") or {}

        if runner_source_factory is None:
            from app import _build_runner_script

            runner_source_factory = _build_runner_script

        with tempfile.TemporaryDirectory(prefix="competitive-audit-worker-") as name:
            run_dir = Path(name)
            runner_path = run_dir / "notebook_runner.py"
            log_path = run_dir / "audit.log"
            source = runner_source_factory(
                audit["company_name"],
                audit["company_domain"],
                audit.get("audit_focus") or "",
                audit["country_code"],
                options.get("search_engine", "auto"),
                "reddit" in (options.get("social_sources") or []),
                bool(options.get("debug", False)),
            )
            compile(source, str(runner_path), "exec")
            runner_path.write_text(source, encoding="utf-8")
            child_env = os.environ.copy()
            child_env["PYTHONUNBUFFERED"] = "1"
            child_env.setdefault("XDG_CACHE_HOME", str(run_dir / ".cache"))
            process = subprocess.Popen(
                [python_executable, "-u", str(runner_path)],
                cwd=run_dir,
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            stop_heartbeat = threading.Event()

            def heartbeat():
                while not stop_heartbeat.wait(heartbeat_interval):
                    try:
                        if not gateway.heartbeat_audit(execution_id, claim_token):
                            process.terminate()
                            return
                    except BackendError:
                        # A transient database outage must not restart paid work.
                        pass

            heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
            heartbeat_thread.start()
            active_step = None
            try:
                assert process.stdout is not None
                with process.stdout, log_path.open("w", encoding="utf-8") as log_file:
                    for line in process.stdout:
                        log_file.write(line)
                        log_file.flush()
                        match = STAGE_LINE.match(line.strip())
                        if not match:
                            continue
                        label = match.group(1).strip()
                        step_key = _step_key(label)
                        try:
                            if active_step is not None:
                                gateway.record_step(
                                    audit_id, active_step[0], active_step[1], "completed"
                                )
                            gateway.record_step(audit_id, step_key, label, "running")
                            gateway.record_event(
                                audit_id, execution_id, "stage_started", label,
                                step_key=step_key,
                            )
                        except BackendError:
                            pass
                        active_step = (step_key, label)
                return_code = process.wait()
            finally:
                stop_heartbeat.set()
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                heartbeat_thread.join(timeout=5)

            artifacts = [log_path, *collect_artifacts(run_dir)]
            report_path = next(
                (path for path in artifacts if _artifact_kind(path) == "json_report"),
                None,
            )
            for artifact in artifacts:
                _publish_artifact(gateway, audit, audit_id, artifact)

            if return_code != 0 or report_path is None:
                if active_step is not None:
                    gateway.record_step(
                        audit_id, active_step[0], active_step[1], "failed"
                    )
                gateway.finish_audit(
                    execution_id,
                    claim_token,
                    "failed",
                    error_code="runner_failed",
                    error_message=(
                        f"Notebook runner exited with status {return_code}"
                        if return_code != 0
                        else "Notebook runner produced no final JSON report"
                    ),
                )
                return 1

            report = json.loads(report_path.read_text(encoding="utf-8"))
            usage = report.get("bright_data_usage") or {}
            gateway.record_usage_operations(_usage_rows(audit_id, execution_id, usage))
            if active_step is not None:
                gateway.record_step(
                    audit_id, active_step[0], active_step[1], "completed"
                )
            usage_summary = {key: value for key, value in usage.items() if key != "events"}
            if not gateway.finish_audit(
                execution_id,
                claim_token,
                "completed",
                summary=_report_summary(report),
                usage_summary=usage_summary,
                report_schema_version=1,
            ):
                raise RuntimeError("Audit claim was lost before completion")
            return 0
    except Exception as exc:
        # Do not put raw exception text in the database; it may contain source
        # data or provider response details. Cloud Run keeps the traceback.
        try:
            gateway.finish_audit(
                execution_id,
                claim_token,
                "failed",
                error_code=type(exc).__name__[:100],
                error_message="Worker failed while running or publishing the audit",
            )
        except Exception:
            pass
        raise


def main():
    gateway = SupabaseGateway(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_PUBLISHABLE_KEY"],
        os.environ["SUPABASE_SECRET_KEY"],
    )
    audit_id = UUID(os.environ["AUDIT_ID"])
    return run_worker(
        gateway,
        audit_id,
        platform_execution_id=os.getenv("CLOUD_RUN_EXECUTION"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
