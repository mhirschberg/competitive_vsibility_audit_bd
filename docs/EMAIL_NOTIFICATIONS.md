# Report-ready email notifications

This is an optional transactional notification for registered **personal trial** audits. Anonymous workshop audits remain frictionless and do not collect email addresses. Closing the browser never stops an audit; the email is only a convenience link back to the signed-in user's private history.

## Flow

1. The web form shows **Email me when the report is ready** only when the API advertises the capability and the user is signed in with Google.
2. The API accepts `email_when_ready` only for personal audits. It stores the choice with the audit input; it never trusts an email address supplied by the browser.
3. When an audit reaches `completed`, a database trigger inserts one outbox row using the email from Supabase Auth. No row is created for failed, interrupted, or anonymous workshop audits.
4. The existing per-audit watchdog continues to its next scheduled check. On a completed audit it claims the outbox row, sends one link through Resend, and marks the row sent. A transient mail failure schedules another check; the completed report stays completed.
5. The email links to `/#history`. The report and files remain behind Google sign-in and normal row-level security. No PDF, raw data, or signed download URL is emailed.

The outbox claim prevents two watchdog calls from sending concurrently. Resend receives a stable `Idempotency-Key: audit-ready/<audit-id>` so routine retries do not duplicate the email. Resend currently retains such keys for 24 hours; this is not an absolute exactly-once guarantee after a prolonged outage. The outbox stops automatic retries after eight attempts and leaves an `abandoned` state for inspection.

## Activation checklist

The feature is **off by default**. Do not set `EMAIL_NOTIFICATIONS_ENABLED=true` until all of these are complete:

1. Apply `20260928000000_audit_email_notifications.sql` in Supabase and verify its service-only functions.
2. Choose and verify a sending domain in Resend. Create a send-only API key; do not put it in Git or public web configuration.
3. Store the key in Google Secret Manager. Grant the **watchdog** service account access to that secret only.
4. Configure the watchdog service with `RESEND_API_KEY`, `NOTIFICATION_FROM_EMAIL` (for example, `reports@your-domain.example`), and `NOTIFICATION_WEB_URL` (the HTTPS web-app origin). Deploy the watchdog code.
5. Send a test email to an account you control, verify the private link, then test a provider failure and retry.
6. Deploy the API and web code. Only after the end-to-end test, set `EMAIL_NOTIFICATIONS_ENABLED=true` on the API. The web switch then appears automatically for signed-in personal users.

Supabase's default Auth SMTP is not used for these report emails. Its built-in sender is intended for development and is not a production transactional mail service.

## Live deployment status (2026-09-28)

The migration is applied in the separate Competitive Audit Supabase project.
The API, private watchdog, and original Cloud Run web UI run in Google Cloud
project `getmuzoboz` (`europe-west1`); the branded static UI runs in Firebase
Hosting project `qaviso-web`. Among application service identities,
only the watchdog can read Secret Manager secret
`competitive-audit-resend-api-key:1`; its sender is
`no-reply@notify.qaviso.com`. The web UI shows the opt-in only for signed-in
personal trials, and the API rejects it for workshop audits. Since 2026-09-28,
the watchdog uses `https://audit.qaviso.com` for private-history links in
report-ready emails. Supabase Auth uses the same branded origin as its Site URL;
the original Cloud Run web URL remains an allowed redirect fallback.

The verified sending domain accepted a Resend delivery-sink test, and a separate
test message reached the owner's mailbox. The Supabase outbox table and
service-only RPCs respond correctly; an anonymous claim is denied. The checkbox
is visible in the signed-in personal-trial form. A full real-audit completion
and subsequent watchdog delivery has **not** yet been exercised; observe the
first opted-in completion before calling the flow end-to-end verified.
