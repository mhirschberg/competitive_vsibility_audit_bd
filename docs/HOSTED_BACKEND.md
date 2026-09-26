# Hosted audit backend: current state and deployment checklist

The separate Competitive Audit Supabase project applies migrations from
`main`. The API, static UI, private watchdog service, and per-audit worker Job
are deployed to Cloud Run in `getmuzoboz` / `europe-west1`. A full Notion audit
completed on 2026-09-26 and produced downloadable report artifacts. The
notebook was not changed for hosting. This is still a workshop deployment:
raise the workshop admission caps deliberately before inviting attendees.

## Live smoke deployment

- Web UI: `https://competitive-audit-web-4lvms3qmsa-ew.a.run.app`
- API health: `https://competitive-audit-api-4lvms3qmsa-ew.a.run.app/health`
- Google Cloud project/region: `getmuzoboz` / `europe-west1`
- Supabase project ref: `xhntpuwntpftjqmlzxgk` (the separate Competitive Audit project)
- A bare Web UI URL points to the bounded `deployment-smoke-test-20260926`
  workshop. Its cap is two total audits, both used by deployment tests. The
  organizer panel at `/admin` creates separate, finite-cap workshop links of
  the form `/?workshop=slug`; creating a new workshop no longer requires a
  web rebuild. Do not simply remove the caps.

## Intended flow

1. A visitor signs in with Supabase Auth and submits one audit to the API.
2. `submit_audit` stores the request with a client UUID, making browser retries
   idempotent. Workshop total and per-user limits are checked transactionally.
3. The API schedules one delayed, authenticated Cloud Task for that audit,
   reserves a workshop concurrency slot, and starts one Cloud Run Job. The
   private watchdog service checks that audit every two minutes while it is
   active. Each successful check schedules exactly one successor; a terminal
   audit ends the chain. Failed checks are retried by Cloud Tasks. A separate
   manual reconciler Job can repair queued or uncertain dispatches.
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
| Organizer permissions, settings functions, and change log | `supabase/migrations/20260926010000_workshop_admin.sql` |
| API | `hosted/api.py` |
| One-audit worker | `hosted/worker.py` |
| Dispatch reconciliation | `hosted/reconcile.py` |
| Per-audit delayed checks | `hosted/watchdog_tasks.py`, `hosted/watchdog.py` |
| Container definitions and Cloud Build recipes | `hosted/Dockerfile.api`, `hosted/Dockerfile.worker`, `hosted/cloudbuild.yaml`, `hosted/cloudbuild-web.yaml`, `web/Dockerfile` |
| Static participant and organizer UIs | `web/` |
| Database design and remaining risks | `docs/SUPABASE_DATABASE.md` |

## Configuration, by component

`SUPABASE_URL` is **one** project URL, such as
`https://PROJECT-REF.supabase.co`. It has the same name everywhere; there is no
second URL to copy. Do not commit `.env.local` or put a secret key in a static
site. The repository's `.dockerignore` also excludes `.env` files from images.

| Variable | Where it goes | Source |
| --- | --- | --- |
| `SUPABASE_URL` | API, watchdog, worker, browser UI | Supabase project's API URL |
| `SUPABASE_PUBLISHABLE_KEY` | API, watchdog, worker, browser UI | Supabase publishable key (`sb_publishable_…`) |
| `SUPABASE_SECRET_KEY` | API, watchdog, worker **only** | Supabase secret key (`sb_secret_…`), supplied through Google Secret Manager |
| `BRIGHTDATA_API_TOKEN` | Worker **only** | Existing Bright Data token, supplied through Secret Manager |
| `SERP_ZONE` | Worker **only** | Existing Bright Data SERP zone name |
| `GOOGLE_CLOUD_PROJECT` | API, watchdog, reconciler | Google Cloud project ID, not display name |
| `CLOUD_RUN_REGION` | API, watchdog, reconciler | Region of the worker Job and Cloud Tasks queue |
| `CLOUD_RUN_JOB_NAME` | API, watchdog, reconciler | Deployed worker Job name |
| `WATCHDOG_QUEUE` | API and watchdog | Cloud Tasks queue name |
| `WATCHDOG_URL` | API and watchdog | Default URL of the private watchdog Cloud Run service |
| `WATCHDOG_INVOKER_EMAIL` | API and watchdog | Task identity allowed to invoke only the private watchdog service |
| `ENGINE_COMMIT` | API | Git commit SHA of the code inside the worker image |
| `METHODOLOGY_VERSION` | API | Explicit method label, initially `v1` |
| `WEB_ORIGIN` | API | Exact HTTPS origin of the future static UI, for CORS |
| `AUDIT_ID` | Worker execution override | Set by the API for each Job; never configure as a fixed Job variable |
| `AUDIT_API_URL` | Static UI build only | Public HTTPS URL of the deployed API |
| `WORKSHOP_ID` | Static UI build only | UUID of the default workshop row; organizer links select another workshop by slug |

The API does **not** need Bright Data credentials. The browser needs only the
publishable key, URL, API address, and workshop identifier. `web/scripts/build-config.mjs`
reads the same root `.env.local` during local development and emits a public
`config.json` without secrets; on a static host, set those four variables in
its build environment. The worker does not receive any user's Auth token.

## Organizer access

The `/admin` page signs in through Supabase Auth's Google provider, using an
OAuth web client configured in the `getmuzoboz` Google Auth Platform project.
The provider requests only `openid`, email, and profile. Allow the exact
`https://competitive-audit-web-4lvms3qmsa-ew.a.run.app/admin` redirect in
Supabase Auth. Organizer login uses a separate browser session store, so it
does not replace the anonymous session that owns a participant's audit history.

Google sign-in alone grants **no** workshop administration. The API validates
the Supabase session with Auth and requires a non-anonymous Google identity;
the database functions additionally require `owner` or `admin` membership in
a team organizer workspace. Bootstrap the intended Google user ID into a
team workspace in `workspace_members` and assign existing workshops to that
workspace through a one-time admin operation. Never grant a role by matching
an email passed from the browser. The browser never receives the Supabase
secret key. New and changed workshop limits are recorded in
`workshop_admin_events`.

The organizer can set opening/closing times and finite total, concurrent,
and per-participant audit caps. Lowering caps blocks future admissions or
dispatch; it does not cancel work already running. `budget_usd` is **not** an
enforced dollar limit and is deliberately absent from the organizer form.

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
4. Build and deploy the API and worker images from the same commit with
   `hosted/cloudbuild.yaml`. Give the API service identity
   permission to execute the worker Job **with overrides** (only `AUDIT_ID` is
   overridden). Give each service identity access only to its required secrets.
   Configure the worker Job as one task with **zero automatic retries** and a
   timeout long enough for a complete audit; a retry must not repeat paid work.
5. Create a Cloud Tasks queue and private watchdog Cloud Run service. Give API
   and watchdog identities `roles/cloudtasks.enqueuer` on that queue and
   `roles/iam.serviceAccountUser` only on the task-invoker identity. Give the
   task-invoker identity `roles/run.invoker` only on the private service. The
   watchdog identity also needs the Supabase secret and permission to execute
   the worker Job with overrides. Cloud Tasks retries transient failures; the
   deterministic task name makes duplicate API submissions safe. Keep the
   manual `python -m hosted.reconcile` Job for recovery. The deployed
   `competitive-audit-daily-recovery` Cloud Scheduler trigger runs that Job
   once per day as a low-frequency safety sweep for stranded dispatches and
   stale workers. It does not recreate a lost per-audit check chain.
6. Build the static UI container with `hosted/cloudbuild-web.yaml` and publish
   it only after its `AUDIT_API_URL` and `WORKSHOP_ID` exist. The image bakes in
   **public** configuration only. It signs in anonymously only when someone submits,
   keeps the audit ID across reloads, and reads history under that user's RLS
   policy. Implement Storage retention cleanup. Test a concurrent room-sized
   burst before replacing the current Gradio app.

Verified so far: Python unit tests, SQL migration/RLS tests, a full live audit
through the public UI/API/worker/Supabase path, refresh recovery, and a private
Cloud Task invocation that ended when it found a completed audit, and a live
Canva audit whose first private check scheduled its successor. Room-sized
concurrency still needs a deliberate live test.
