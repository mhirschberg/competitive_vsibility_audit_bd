# Cost visibility and Supabase preflight

## Owner dashboard

Open `/admin` and sign in with the site-owner Google account. The **Cost & capacity** tab shows all-time audit counts, Bright Data operations and confirmed results, its recorded cost estimate, retained report-file size, and recorded worker time. Purged workshop totals are kept in the aggregate; purged files and runtime details are intentionally absent.

The estimate is **not** a bill. It can omit operations with unknown prices and includes lower-bound estimates. Uncertainty counts cover retained operations only because purge removes detailed records. The calculator models only Cloud Run Job compute at the current list rates for a 2-vCPU/2-GiB worker. It ignores free tier, trial credit, startup/billing differences, the API and web services, networking, Supabase, and Bright Data. Use the three provider links for actual invoices and usage.

The tab is protected by `site_admins`, the same explicit site-owner allowlist as the registered-users view. SQL migration `20260927010000_admin_cost_overview.sql` must be applied before deploying the new API and web images.

## Waking Supabase before a workshop

Supabase Free may pause an inactive project. A scheduled SQL job or Edge Function inside that project cannot run once it is paused. The supported recovery path is the Supabase Management API **restore project** operation, run from outside Supabase.

The repository includes a read-only check and opt-in restore script:

```sh
export SUPABASE_ACCESS_TOKEN='…'  # from Supabase Account > Access Tokens; do not commit it
python scripts/wake_supabase.py --project-ref xhntpuwntpftjqmlzxgk
python scripts/wake_supabase.py --project-ref xhntpuwntpftjqmlzxgk --restore
```

The script first checks the project and calls restore **only if** its status is `INACTIVE`. It waits for `ACTIVE_HEALTHY` and exits nonzero on failure. A healthy project is left untouched.

For one-click use, add a repository secret named `SUPABASE_MANAGEMENT_TOKEN` in GitHub **Settings → Secrets and variables → Actions**, then run **Actions → Wake Supabase before a workshop → Run workflow**. The token needs `project_admin_read` and `project_admin_write` permission for this specific project. That write scope can also perform other project-administration actions, so create a separate scoped token, restrict it to this project if offered, and treat GitHub repository administrators as trusted holders of this capability. Never put the token in the repository or browser-side code.

The workflow is deliberately **manual**, not a daily keep-alive: a monthly workshop does not need a continuously active free database. Run it before participants arrive, then open the site and do a small test audit. This only wakes Supabase; it cannot reactivate a Google Cloud free trial after its trial period ends.

Official references: [Supabase project pausing](https://supabase.com/docs/guides/platform/free-project-pausing), [restore-project API](https://supabase.com/docs/reference/api/v1-restore-a-project), [Cloud Run pricing](https://cloud.google.com/run/pricing).
