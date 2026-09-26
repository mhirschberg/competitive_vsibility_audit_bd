"""Schedule one delayed, authenticated check for a specific audit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import requests


class WatchdogError(Exception):
    pass


class AuditWatchdogTasks:
    def __init__(
        self,
        project_id: str,
        region: str,
        queue_name: str,
        target_url: str,
        invoker_email: str,
        *,
        delay_seconds: int = 120,
        session: requests.Session | None = None,
    ):
        for name, value in (
            ("project_id", project_id),
            ("region", region),
            ("queue_name", queue_name),
        ):
            if not value or not value.replace("-", "").isalnum():
                raise ValueError(f"Invalid {name}")
        if not target_url.startswith("https://") or not target_url.endswith(".run.app"):
            raise ValueError("Watchdog target must be a Cloud Run URL")
        if not invoker_email.endswith(".iam.gserviceaccount.com"):
            raise ValueError("Invalid watchdog invoker account")
        if not 30 <= delay_seconds <= 3600:
            raise ValueError("Invalid watchdog delay")
        self.queue_path = (
            f"projects/{project_id}/locations/{region}/queues/{queue_name}"
        )
        self.target_url = target_url
        self.invoker_email = invoker_email
        self.delay_seconds = delay_seconds
        self.session = session or requests.Session()

    def schedule(self, audit_id: UUID, sequence: int = 0) -> None:
        if sequence < 0 or sequence > 1000000:
            raise ValueError("Invalid watchdog sequence")
        task_name = f"{self.queue_path}/tasks/watch-{audit_id.hex}-{sequence:07d}"
        scheduled_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.delay_seconds
        )
        try:
            token_response = self.session.get(
                "http://metadata.google.internal/computeMetadata/v1/"
                "instance/service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"},
                timeout=5,
            )
            token_response.raise_for_status()
            token = token_response.json()["access_token"]
            response = self.session.post(
                f"https://cloudtasks.googleapis.com/v2/{self.queue_path}/tasks",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "task": {
                        "name": task_name,
                        "scheduleTime": scheduled_at.isoformat().replace("+00:00", "Z"),
                        "httpRequest": {
                            "httpMethod": "POST",
                            "url": f"{self.target_url}/watch/{audit_id}/{sequence}",
                            "oidcToken": {
                                "serviceAccountEmail": self.invoker_email,
                                "audience": self.target_url,
                            },
                        },
                    }
                },
                timeout=20,
            )
            # Cloud Tasks retains completed names for deduplication. A retry of
            # the same API request or check must not create another chain.
            if response.status_code != 409:
                response.raise_for_status()
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise WatchdogError("Could not schedule audit health check") from exc
