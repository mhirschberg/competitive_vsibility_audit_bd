"""Execute one existing Cloud Run Job with an audit ID override."""

from __future__ import annotations

from uuid import UUID

import requests


class DispatchError(Exception):
    pass


class CloudRunDispatcher:
    def __init__(
        self,
        project_id: str,
        region: str,
        job_name: str,
        *,
        session: requests.Session | None = None,
    ):
        for label, value in (
            ("GOOGLE_CLOUD_PROJECT", project_id),
            ("CLOUD_RUN_REGION", region),
            ("CLOUD_RUN_JOB_NAME", job_name),
        ):
            if not value or not value.replace("-", "").isalnum():
                raise ValueError(f"Invalid {label}")
        self.project_id = project_id
        self.region = region
        self.job_name = job_name
        self.session = session or requests.Session()

    def dispatch(self, audit_id: UUID) -> str:
        try:
            token_response = self.session.get(
                "http://metadata.google.internal/computeMetadata/v1/"
                "instance/service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"},
                timeout=5,
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]
            response = self.session.post(
                "https://run.googleapis.com/v2/projects/"
                f"{self.project_id}/locations/{self.region}/jobs/"
                f"{self.job_name}:run",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "overrides": {
                        "containerOverrides": [
                            {
                                "env": [
                                    {"name": "AUDIT_ID", "value": str(audit_id)}
                                ]
                            }
                        ],
                        "taskCount": 1,
                    }
                },
                timeout=20,
            )
            response.raise_for_status()
            return str(response.json()["name"])
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            # Do not log token, request headers, or provider response body.
            raise DispatchError("Cloud Run job dispatch failed") from exc
