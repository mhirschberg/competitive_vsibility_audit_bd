# Hosted audit backend: current state and deployment checklist

This is a **local prototype, not a deployed replacement** for the current
Gradio workshop app. The separate Competitive Audit Supabase project is
connected to this repository and set to apply migrations from `main`, but this
migration has not been merged or applied yet. No Cloud Run service/job has
been created. The static UI exists locally but is not published. The notebook
is unchanged.

## Intended flow

1. A visitor signs in with Supabase Auth and submits one audit to the API.
2. `submit_audit` stores the request with a client UUID, making browser retries
   idempotent. Workshop total and per-user limits are checked transactionally.
3. The API reserves a workshop concurrency slot and starts one Cloud Run Job.
   A scheduled reconciler can retry a queued or uncertain dispatch.
4. The Job claims the audit before any Bright Data call, runs the existing
   notebook through the existing web wrapper, sends heartbeats and stage
   events, and uploads the log and reports to private Supabase Storage.
5. The browser reloads `/audits/{id}` after any refresh. Reads use the visitor's
   own Supabase session and database row-level security. A dead worker is
   marked `interrupted`, not automatically rerun and re-billed.

## Files

| Purpose | File |
| --- | --- |
| Database schema, access rules, admission/claim/heartbeat functions | `supabase/migrations/20260926000000_audit_foundation.sql` |
| API | `hosted/api.py` |
| One-audit worker | `hosted/worker.py` |
| Dispatch reconciliation | `hosted/reconcile.py` |
| Container definitions | `hosted/Dockerfile.api`, `hosted/Dockerfile.worker` |
| Static participant UI | `web/` |
| Database design and remaining risks | `docs/SUPABASE_DATABASE.md` |

## Configuration, by component

`SUPABASE_URL` is **one** project URL, such as
`https://PROJECT-REF.supabase.co`. It has the same name everywhere; there is no
second URL to copy. Do not commit `.env.local` or put a secret key in a static
site. The repository's `.dockerignore` also excludes `.env` files from images.

| Variable | Where it goes | Source |
| --- | --- | --- |
| `SUPABASE_URL` | API, worker, future browser UI | Supabase project's API URL |
| `SUPABASE_PUBLISHABLE_KEY` | API, worker, future browser UI | Supabase publishable key (`sb_publishable_…`) |
| `SUPABASE_SECRET_KEY` | API and worker **only** | Supabase secret key (`sb_secret_…`), supplied through Google Secret Manager |
| `BRIGHTDATA_API_TOKEN` | Worker **only** | Existing Bright Data token, supplied through Secret Manager |
| `SERP_ZONE` | Worker **only** | Existing Bright Data SERP zone name |
| `GOOGLE_CLOUD_PROJECT` | API and reconciler | Google Cloud project ID, not display name |
| `CLOUD_RUN_REGION` | API and reconciler | Region of the worker Job |
| `CLOUD_RUN_JOB_NAME` | API and reconciler | Deployed worker Job name |
| `ENGINE_COMMIT` | API | Git commit SHA of the code inside the worker image |
| `METHODOLOGY_VERSION` | API | Explicit method label, initially `v1` |
| `WEB_ORIGIN` | API | Exact HTTPS origin of the future static UI, for CORS |
| `AUDIT_ID` | Worker execution override | Set by the API for each Job; never configure as a fixed Job variable |
| `AUDIT_API_URL` | Static UI build only | Public HTTPS URL of the deployed API |
| `WORKSHOP_ID` | Static UI build only | UUID of the workshop row in this Supabase project |

The API does **not** need Bright Data credentials. The browser needs only the
publishable key, URL, API address, and workshop identifier. `web/scripts/build-config.mjs`
reads the same root `.env.local` during local development and emits a public
`config.json` without secrets; on a static host, set those four variables in
its build environment. The worker does not receive any user's Auth token.

## Before exposing it to workshop attendees

1. Keep the versioned migration in Git and connect the **separate** Competitive
   Audit Supabase project to this repository. Configure the repository root
   (`.`) as the working directory and `main` as the production branch; after
   review and merge, Supabase applies pending migrations from
   `supabase/migrations/`. The migration has already passed isolated
   PostgreSQL tests and an opt-in integration test in the full local Supabase
   stack. Never use `supabase db reset --linked` on the hosted project.
2. Enable anonymous Auth only with an abuse policy. Supabase currently defaults
   to 30 anonymous sign-ins per hour per IP, which a shared workshop Wi-Fi can
   exceed. Rehearse sign-in and adjust the limit/protection deliberately.
3. Create a workshop record with a finite `max_total_audits`,
   `max_audits_per_user`, and `max_concurrent_audits`. `budget_usd` is recorded
   but **not enforced**; the total cap is the present spend backstop.
4. Build and deploy the API and worker images. Give the API service identity
   permission to execute the worker Job **with overrides** (only `AUDIT_ID` is
   overridden). Give each service identity access only to its required secrets.
   Configure the worker Job as one task with **zero automatic retries** and a
   timeout long enough for a complete audit; a retry must not repeat paid work.
5. Schedule `python -m hosted.reconcile` with the API image and the same
   configuration as the API. The first version should run every minute or two.
   Without this schedule, a dispatch error can leave a request pending.
6. Publish the static UI in `web/` only after its `AUDIT_API_URL` and
   `WORKSHOP_ID` exist. It signs in anonymously only when someone submits,
   keeps the audit ID across reloads, and reads history under that user's RLS
   policy. Implement Storage retention cleanup. Test a full audit and a concurrent room-sized
   burst before replacing the current Gradio app.

Locally verified so far: Python unit tests, API and worker container builds,
static UI build and desktop/mobile visual inspection, runner generation/
compilation inside the worker image, SQL migration/RLS tests in a throwaway
PostgreSQL 16 container, and an opt-in local Supabase Auth/REST/RLS/Storage
integration test (`RUN_SUPABASE_INTEGRATION=1`). The latter checks real
anonymous sign-in, idempotent submission, cross-user isolation, worker claim,
private upload, and signed download without calling Bright Data.
No live Supabase, Cloud Run, or Bright Data end-to-end test has been run.
