"""Small server-only Supabase HTTP gateway using the new API key types."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import UUID

import requests


class AuthenticationError(Exception):
    pass


class SubmissionError(Exception):
    pass


class BackendError(Exception):
    pass


class SupabaseGateway:
    def __init__(
        self,
        url: str,
        publishable_key: str,
        secret_key: str,
        *,
        session: requests.Session | None = None,
        allow_local_http: bool = False,
    ):
        self.url = url.rstrip("/")
        parsed = urlsplit(self.url)
        local_http = (
            allow_local_http
            and parsed.scheme == "http"
            and parsed.hostname in ("127.0.0.1", "localhost")
            and parsed.port is not None
        )
        hosted_https = (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.hostname.endswith(".supabase.co")
            and parsed.port is None
        )
        if (
            not (local_http or hosted_https)
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("SUPABASE_URL must be an HTTPS Supabase project URL")
        if not publishable_key.startswith("sb_publishable_"):
            raise ValueError("SUPABASE_PUBLISHABLE_KEY must be a publishable key")
        if not secret_key.startswith("sb_secret_"):
            raise ValueError("SUPABASE_SECRET_KEY must be a secret key")
        self.publishable_key = publishable_key
        self.secret_key = secret_key
        self.session = session or requests.Session()

    def authenticate(self, bearer_token: str) -> UUID:
        """Ask Supabase Auth to validate the user's JWT; never trust its claims locally."""
        if not bearer_token:
            raise AuthenticationError("Missing bearer token")
        try:
            response = self.session.get(
                f"{self.url}/auth/v1/user",
                headers={
                    "apikey": self.publishable_key,
                    "Authorization": f"Bearer {bearer_token}",
                },
                timeout=10,
            )
        except requests.RequestException as exc:
            raise BackendError("Authentication service unavailable") from exc
        if response.status_code in (401, 403):
            raise AuthenticationError("Invalid or expired session")
        if not response.ok:
            raise BackendError("Authentication service unavailable")
        try:
            return UUID(response.json()["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BackendError("Invalid authentication response") from exc

    def _rpc(self, name: str, payload: dict):
        try:
            response = self.session.post(
                f"{self.url}/rest/v1/rpc/{name}",
                headers={
                    "apikey": self.secret_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise BackendError("Database service unavailable") from exc
        if not response.ok:
            try:
                code = response.json().get("code")
            except (TypeError, ValueError):
                code = None
            if code == "22023":
                raise SubmissionError("Audit request or workshop limit invalid")
            if code == "42501":
                raise AuthenticationError("Not allowed to use this workspace")
            raise BackendError("Database operation failed")
        try:
            return response.json()
        except ValueError as exc:
            raise BackendError("Invalid database response") from exc

    def submit_audit(self, **payload) -> UUID:
        result = self._rpc("submit_audit", payload)
        try:
            return UUID(result)
        except (TypeError, ValueError) as exc:
            raise BackendError("Invalid audit ID from database") from exc

    def reserve_dispatch(self, audit_id: UUID) -> bool:
        result = self._rpc(
            "reserve_audit_dispatch", {"p_audit_id": str(audit_id)}
        )
        if not isinstance(result, bool):
            raise BackendError("Invalid dispatch reservation response")
        return result

    def interrupt_stale_audits(self) -> int:
        result = self._rpc("interrupt_stale_audits", {})
        if not isinstance(result, int) or isinstance(result, bool) or result < 0:
            raise BackendError("Invalid stale-audit response")
        return result

    def list_dispatch_candidates(self, limit: int = 50) -> list[UUID]:
        """Find queued and timed-out dispatches for the scheduled reconciler."""
        limit = min(max(limit, 1), 100)
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        candidates = []
        for filters in (
            {
                "status": "eq.dispatching",
                "last_dispatch_at": f"lt.{cutoff}",
                "order": "last_dispatch_at.asc",
            },
            {"status": "eq.queued", "order": "created_at.asc"},
        ):
            try:
                response = self.session.get(
                    f"{self.url}/rest/v1/audits",
                    headers={"apikey": self.secret_key},
                    params={"select": "id", "limit": str(limit), **filters},
                    timeout=15,
                )
            except requests.RequestException as exc:
                raise BackendError("Database service unavailable") from exc
            if not response.ok:
                raise BackendError("Cannot list pending audits")
            try:
                candidates.extend(UUID(row["id"]) for row in response.json())
            except (KeyError, TypeError, ValueError) as exc:
                raise BackendError("Invalid pending audit response") from exc
        return list(dict.fromkeys(candidates))[:limit]

    def _admin_request(self, method: str, path: str, **kwargs):
        headers = {"apikey": self.secret_key, **kwargs.pop("headers", {})}
        try:
            response = self.session.request(
                method,
                f"{self.url}{path}",
                headers=headers,
                timeout=kwargs.pop("timeout", 20),
                **kwargs,
            )
        except requests.RequestException as exc:
            raise BackendError("Database or storage service unavailable") from exc
        if not response.ok:
            raise BackendError("Database or storage operation failed")
        return response

    def _user_list(self, path: str, bearer_token: str, **params) -> list[dict]:
        try:
            response = self.session.get(
                f"{self.url}/rest/v1/{path}",
                headers={
                    "apikey": self.publishable_key,
                    "Authorization": f"Bearer {bearer_token}",
                },
                params=params,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise BackendError("Database service unavailable") from exc
        if response.status_code in (401, 403):
            raise AuthenticationError("Invalid or expired session")
        if not response.ok:
            raise BackendError("Database read failed")
        try:
            rows = response.json()
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise TypeError("Expected a list of records")
            return rows
        except (TypeError, ValueError) as exc:
            raise BackendError("Invalid database response") from exc

    def read_audit_status(self, audit_id: UUID, bearer_token: str) -> dict | None:
        """Read through RLS, so another user's audit is indistinguishable from missing."""
        rows = self._user_list(
            "audits",
            bearer_token,
            select=(
                "id,company_name,company_domain,audit_focus,country_code,"
                "status,created_at,started_at,finished_at,updated_at,"
                "summary,usage_summary,error_code,error_message,expires_at"
            ),
            id=f"eq.{audit_id}",
            limit="1",
        )
        if not rows:
            return None
        audit = rows[0]
        audit["steps"] = self._user_list(
            "audit_steps",
            bearer_token,
            select="step_key,label,status,progress_current,progress_total,updated_at",
            audit_id=f"eq.{audit_id}",
            order="updated_at.asc",
        )
        audit["events"] = self._user_list(
            "audit_events",
            bearer_token,
            select="id,step_key,event_kind,severity,message,created_at",
            audit_id=f"eq.{audit_id}",
            order="id.desc",
            limit="100",
        )
        audit["artifacts"] = self._user_list(
            "audit_artifacts",
            bearer_token,
            select="id,kind,content_type,size_bytes,created_at",
            audit_id=f"eq.{audit_id}",
            order="created_at.asc",
        )
        return audit

    def sign_artifact_for_user(
        self, audit_id: UUID, artifact_id: UUID, bearer_token: str
    ) -> str | None:
        """Authorize through user RLS before minting a short-lived capability URL."""
        rows = self._user_list(
            "audit_artifacts",
            bearer_token,
            select="bucket_id,object_path",
            id=f"eq.{artifact_id}",
            audit_id=f"eq.{audit_id}",
            limit="1",
        )
        if not rows:
            return None
        artifact = rows[0]
        if artifact.get("bucket_id") != "audit-artifacts":
            raise BackendError("Unexpected artifact bucket")
        object_path = artifact.get("object_path")
        if not isinstance(object_path, str) or not object_path:
            raise BackendError("Invalid artifact path")
        encoded_path = quote(object_path, safe="/")
        response = self._admin_request(
            "POST",
            f"/storage/v1/object/sign/audit-artifacts/{encoded_path}",
            headers={"Content-Type": "application/json"},
            json={"expiresIn": 300},
        )
        try:
            signed_path = response.json()["signedURL"]
        except (KeyError, TypeError, ValueError) as exc:
            raise BackendError("Invalid Storage signing response") from exc
        expected_path = f"/object/sign/audit-artifacts/{encoded_path}"
        if (
            not isinstance(signed_path, str)
            or signed_path.split("?", 1)[0] != expected_path
            or "?token=" not in signed_path
        ):
            raise BackendError("Invalid Storage signing response")
        return f"{self.url}/storage/v1{signed_path}"

    def get_audit(self, audit_id: UUID) -> dict:
        response = self._admin_request(
            "GET",
            "/rest/v1/audits",
            params={"select": "*", "id": f"eq.{audit_id}", "limit": "1"},
        )
        try:
            rows = response.json()
            if len(rows) != 1:
                raise BackendError("Audit not found")
            return rows[0]
        except (TypeError, ValueError, KeyError) as exc:
            raise BackendError("Invalid audit response") from exc

    def claim_audit(self, audit_id: UUID, platform_execution_id=None):
        result = self._rpc(
            "claim_audit",
            {
                "p_audit_id": str(audit_id),
                "p_platform_execution_id": platform_execution_id,
            },
        )
        if not isinstance(result, list):
            raise BackendError("Invalid audit claim response")
        if not result:
            return None
        try:
            return UUID(result[0]["execution_id"]), UUID(result[0]["claim_token"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BackendError("Invalid audit claim response") from exc

    def heartbeat_audit(self, execution_id: UUID, claim_token: UUID) -> bool:
        result = self._rpc(
            "heartbeat_audit",
            {
                "p_execution_id": str(execution_id),
                "p_claim_token": str(claim_token),
            },
        )
        if not isinstance(result, bool):
            raise BackendError("Invalid heartbeat response")
        return result

    def finish_audit(
        self,
        execution_id: UUID,
        claim_token: UUID,
        outcome: str,
        *,
        summary=None,
        usage_summary=None,
        report_schema_version=None,
        error_code=None,
        error_message=None,
    ) -> bool:
        result = self._rpc(
            "finish_audit",
            {
                "p_execution_id": str(execution_id),
                "p_claim_token": str(claim_token),
                "p_outcome": outcome,
                "p_summary": summary,
                "p_usage_summary": usage_summary,
                "p_report_schema_version": report_schema_version,
                "p_error_code": error_code,
                "p_error_message": error_message,
            },
        )
        if not isinstance(result, bool):
            raise BackendError("Invalid audit completion response")
        return result

    def record_event(
        self,
        audit_id: UUID,
        execution_id: UUID,
        kind: str,
        message: str,
        *,
        step_key=None,
        severity="info",
    ):
        self._admin_request(
            "POST",
            "/rest/v1/audit_events",
            headers={"Content-Type": "application/json"},
            json={
                "audit_id": str(audit_id),
                "execution_id": str(execution_id),
                "event_kind": kind,
                "step_key": step_key,
                "severity": severity,
                "message": message[:2000],
            },
        )

    def record_step(self, audit_id: UUID, step_key: str, label: str, status: str):
        self._admin_request(
            "POST",
            "/rest/v1/audit_steps",
            headers={
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            },
            params={"on_conflict": "audit_id,step_key"},
            json={
                "audit_id": str(audit_id),
                "step_key": step_key,
                "label": label,
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def upload_artifact(self, object_path: str, file_path: Path, content_type: str):
        encoded_path = quote(object_path, safe="/")
        with file_path.open("rb") as file_stream:
            self._admin_request(
                "POST",
                f"/storage/v1/object/audit-artifacts/{encoded_path}",
                headers={
                    "Content-Type": content_type,
                    "x-upsert": "false",
                },
                data=file_stream,
                timeout=120,
            )

    def record_artifact(self, metadata: dict):
        self._admin_request(
            "POST",
            "/rest/v1/audit_artifacts",
            headers={"Content-Type": "application/json"},
            json=metadata,
        )

    def record_usage_operations(self, rows: list[dict]):
        if not rows:
            return
        self._admin_request(
            "POST",
            "/rest/v1/brightdata_operations",
            headers={
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            },
            params={"on_conflict": "execution_id,source_operation_id"},
            json=rows,
        )
