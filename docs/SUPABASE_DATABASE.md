# Supabase data model for hosted audits

Status: local migration, backend, and static UI prototype; **not yet applied
or deployed to the hosted Supabase/Google Cloud projects**. The versioned migration is
`supabase/migrations/20260926000000_audit_foundation.sql`.

## Boundary between database and report files

Postgres owns identity, admission, status, progress, artifact metadata, and
Bright Data usage. The complete evolving report, raw evidence, full process
log, PDF, Markdown, and ZIP belong in the private `audit-artifacts` Storage
bucket. `audits.summary` and `audits.usage_summary` are small dashboard caches,
not substitutes for the versioned full report. The existing final report JSON
is already over a megabyte for some runs and contains deeply nested SERP, AI,
and social data.

```
workspaces --< workspace_members
     |
     +--< audits >-- workshops (optional)
               |
               +--< audit_executions
               +--< audit_steps
               +--< audit_events
               +--< audit_artifacts --> private Storage objects
               +--< brightdata_operations
```

Each anonymous Supabase Auth user starts with a personal workspace. A later
identity link preserves the Auth user ID and therefore the workspace and its
history. Team workspaces can add members without changing audit ownership.
An audit can be attached to a workshop or run independently.

## Stable audit contract

`audits` contains the searchable input fields plus `input_options` JSONB for
options that will evolve (for example, social sources beyond Reddit). It also
records an input schema version, exact engine commit, methodology version, and
final report schema version. A comparison UI must disclose version differences
instead of treating every changed number as a market change.

The audit ID is the durable status URL. The browser may refresh or reach a
different web replica without losing the run. `(created_by, client_request_id)`
prevents a double click or HTTP retry from submitting a second paid audit.
Manual reruns receive a new audit ID and point to `rerun_of`.

`audit_steps` uses stable string keys such as `serp_discovery` and
`reddit_social`, not fixed step numbers. Several steps may be `running` at
once. `audit_events` is a concise, append-only progress timeline; the complete
stdout/stderr log is a Storage artifact, not thousands of Postgres rows.

`audit_executions` separates a user-visible audit from Cloud Run invocation
attempts. The unique partial index permits at most one running execution per
audit. The worker atomically claims a queued audit before any Bright Data
calls. Heartbeats and the final state change are fenced to its claim token.
A dispatcher can revisit queued/dispatching rows after an uncertain Cloud Run
response; a duplicate worker exits when the claim fails. A stalled running
audit is marked `interrupted` by the local reconciler, never automatically
retried from scratch. The reconciler still needs a live schedule.

The migration includes server-only functions. `submit_audit` creates a
personal workspace when necessary, checks membership, deduplicates by client
request ID, and serializes workshop total/per-user quota checks under a row
lock. `reserve_audit_dispatch` serializes per-workshop dispatch reservations
and enforces `max_concurrent_audits`; a timed-out reservation can be retried by
the local reconciler. `claim_audit` atomically changes one queued/dispatching
audit to running and issues a claim token to one execution. `heartbeat_audit`
and `finish_audit` validate that token; `interrupt_stale_audits` handles a
worker killed before it can report a failure. None of these functions is
callable with the browser's publishable key. The monetary budget is **not**
enforced yet; a conservative workshop run cap must be set before public launch.
The API must derive `p_user_id` from a validated Supabase Auth session, never
from a client-supplied JSON field.

`brightdata_operations` records each actual operation, including every race
candidate that was started. A nullable confirmed result count distinguishes
"zero results" from "not yet known". Rates and estimates are stored per
operation so later price changes do not rewrite historical estimates. The
dashboard should label this an estimate, not an invoice. The current notebook
emits usage details in its completed report; accurate usage on failed runs
will require the worker to persist events as they occur or a small audit-client
hook. The wrapper cannot infer missing billable results from a failed process.

## Security and lifecycle

- Browser users have `SELECT` only, through RLS membership checks. All inserts,
  updates, deletes, quota admission, job claims, and artifact uploads are
  server-only. An anonymous Auth user has Postgres role `authenticated`; it is
  not the same as the public `anon` API key.
- Storage has no browser policy. The local API can mint five-minute signed
  download URLs only after the user's RLS-protected artifact read succeeds.
  This still needs testing against real Supabase Storage. Never put
  `SUPABASE_SECRET_KEY` or the Bright Data token in browser configuration or
  stored audit options.
- Workshop limits must be reserved in one database transaction. A read-then-
  insert sequence outside a transaction can oversubscribe when many attendees
  submit together.
- Retention is captured in `audits.expires_at`. Cleanup must delete Storage
  objects through the Storage API **before** deleting the database rows;
  cascading SQL deletes only artifact metadata, not the underlying files.
- Anonymous sign-ins are rate-limited by IP. A workshop on one shared Wi-Fi
  needs a rehearsal and a configured admission policy; the default limit may
  reject a room full of participants.

## Before applying to the hosted project

1. Install the Supabase CLI and run this migration in a disposable local
   Supabase stack. Verify table constraints and the private Storage bucket.
2. Test RLS with two different Auth users: each sees only their workspace's
   audits and child rows; neither can write directly; an unauthenticated
   client sees nothing. Test signed downloads against Storage separately.
3. Complete the remaining lifecycle work: retention cleanup and scheduling
   the reconciler. The local API/worker
   exercise admission, claim/fencing, heartbeat, interruption, and artifact
   publication in tests, but not against a full Supabase stack.
4. Load-test anonymous sign-in and audit submission from a shared IP before a
   workshop. Set workshop concurrency and total-run caps before enabling access;
   these are only an approximate spend backstop until a real monetary cap exists.
5. Only then apply the reviewed migration to the separate hosted Supabase
   project. Do not use the unrelated PracticeLoop project.

No SQL migration alone makes the current Gradio app durable: it still keeps
jobs in process memory and report files on local disk until the new UI and
worker are deployed against this model.

The repository also contains `supabase/tests/local_postgres_bootstrap.sql` and
`local_postgres_rls.sql`. These passed in a throwaway PostgreSQL 16 container
without network access, checking syntax, isolation of two users, denied browser
writes, idempotent submission, workshop limits, and duplicate worker claims.
They use minimal stand-ins for Supabase-managed schemas and do not replace a
full Supabase local-stack test before hosted deployment.
