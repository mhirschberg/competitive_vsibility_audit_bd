"""Minimal admission API. Start with: uvicorn hosted.api:create_app --factory."""

from __future__ import annotations

import os
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from hosted.cloud_run import CloudRunDispatcher, DispatchError
from hosted.supabase_gateway import (
    AuthenticationError,
    BackendError,
    SubmissionError,
    SupabaseGateway,
)


class AuditRequest(BaseModel):
    client_request_id: UUID
    company_name: str = Field(min_length=1, max_length=300)
    company_domain: str = Field(min_length=1, max_length=500)
    audit_focus: str = Field(default="", max_length=1000)
    country_code: str = Field(default="US", pattern=r"^[A-Za-z]{2}$")
    search_engine: Literal["auto", "google", "bing", "none"] = "auto"
    include_reddit_analysis: bool = False
    workshop_id: UUID


class AuditAccepted(BaseModel):
    audit_id: UUID
    dispatch_state: Literal["started", "already_pending", "pending_retry"]


def create_app(*, gateway=None, dispatcher=None, settings=None) -> FastAPI:
    settings = settings or os.environ
    if gateway is None:
        gateway = SupabaseGateway(
            settings["SUPABASE_URL"],
            settings["SUPABASE_PUBLISHABLE_KEY"],
            settings["SUPABASE_SECRET_KEY"],
        )
    if dispatcher is None:
        dispatcher = CloudRunDispatcher(
            settings["GOOGLE_CLOUD_PROJECT"],
            settings["CLOUD_RUN_REGION"],
            settings["CLOUD_RUN_JOB_NAME"],
        )
    engine_commit = settings.get("ENGINE_COMMIT", "").strip()
    methodology_version = settings.get("METHODOLOGY_VERSION", "").strip()
    if not engine_commit or not methodology_version:
        raise ValueError("ENGINE_COMMIT and METHODOLOGY_VERSION are required")

    app = FastAPI(title="Competitive Visibility Audit API")
    web_origin = settings.get("WEB_ORIGIN", "").strip()
    if web_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[web_origin],
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    # Cloud Run reserves some URL paths ending in "z", including /healthz.
    @app.get("/health")
    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}

    @app.post("/audits", response_model=AuditAccepted, status_code=202)
    def submit_audit(
        request: AuditRequest,
        authorization: str | None = Header(default=None),
    ):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Sign in required")
        bearer_token = authorization.removeprefix("Bearer ").strip()
        try:
            user_id = gateway.authenticate(bearer_token)
            audit_id = gateway.submit_audit(
                p_user_id=str(user_id),
                p_client_request_id=str(request.client_request_id),
                p_company_name=request.company_name.strip(),
                p_company_domain=request.company_domain.strip(),
                p_audit_focus=request.audit_focus.strip(),
                p_country_code=request.country_code.upper(),
                p_input_options={
                    "search_engine": request.search_engine,
                    "social_sources": (
                        ["reddit"] if request.include_reddit_analysis else []
                    ),
                },
                p_engine_commit=engine_commit,
                p_methodology_version=methodology_version,
                p_workshop_id=str(request.workshop_id),
            )
            if not gateway.reserve_dispatch(audit_id):
                return AuditAccepted(
                    audit_id=audit_id, dispatch_state="already_pending"
                )
            try:
                dispatcher.dispatch(audit_id)
            except DispatchError:
                # The row remains dispatching; a scheduled reconciler must
                # revisit it after the reservation timeout.
                return AuditAccepted(
                    audit_id=audit_id, dispatch_state="pending_retry"
                )
            return AuditAccepted(audit_id=audit_id, dispatch_state="started")
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except SubmissionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except BackendError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/audits/{audit_id}")
    def read_audit_status(
        audit_id: UUID,
        authorization: str | None = Header(default=None),
    ):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Sign in required")
        bearer_token = authorization.removeprefix("Bearer ").strip()
        try:
            gateway.authenticate(bearer_token)
            audit = gateway.read_audit_status(audit_id, bearer_token)
            if audit is None:
                raise HTTPException(status_code=404, detail="Audit not found")
            return audit
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except BackendError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/audits/{audit_id}/artifacts/{artifact_id}/download")
    def download_artifact(
        audit_id: UUID,
        artifact_id: UUID,
        authorization: str | None = Header(default=None),
    ):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Sign in required")
        bearer_token = authorization.removeprefix("Bearer ").strip()
        try:
            gateway.authenticate(bearer_token)
            signed_url = gateway.sign_artifact_for_user(
                audit_id, artifact_id, bearer_token
            )
            if signed_url is None:
                raise HTTPException(status_code=404, detail="Artifact not found")
            return {"url": signed_url, "expires_in": 300}
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except BackendError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return app
