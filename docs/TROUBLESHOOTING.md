# Troubleshooting

This guide covers common notebook, local-run, collection, and reporting problems. Start with `DEBUG_MODE = True` when a normal run does not provide enough detail.

## The API token is missing

In Google Colab, confirm that the secret is named exactly:

```text
BRIGHTDATA_API_TOKEN
```

The value must be a valid Bright Data API token and **Notebook access** must be enabled for the secret.

Do not paste the token into a notebook cell or commit it to the repository.

For a local run, put the token in the ignored `.env.local` file:

```text
BRIGHTDATA_API_TOKEN=...
SERP_ZONE=...
```

## Traditional-search requests fail

Confirm that:

- `SERP_ZONE` matches an active Bright Data SERP API zone.
- The API token can access that zone.
- The zone is configured for Markdown output.
- `COUNTRY` is a valid two-letter country code.
- `SEARCH_ENGINE` is `auto`, `google`, `bing`, or `none`.

With `SEARCH_ENGINE = "auto"`, the notebook tries Google first and falls back to Bing when Google remains unavailable.

If neither engine is available, the audit can continue with AI visibility and source analysis. The report should mark traditional search as not measured rather than reporting zero visibility.

## An answer-engine or dataset request is rejected

Confirm that the Bright Data account has access to the relevant dataset:

- Google AI Mode
- ChatGPT
- Gemini
- Reddit posts when social analysis is enabled
- Reddit comments when social analysis is enabled

A valid SERP zone alone does not guarantee access to every answer-engine or social dataset.

## A snapshot takes several minutes

Live answer-engine and dataset snapshots can have variable latency.

The audit starts parallel races in latency-sensitive stages and retains the first result that passes validation. A snapshot can finish first but still lose if it contains empty content, interface boilerplate, invalid JSON, or incomplete task data.

Enable:

```python
DEBUG_MODE = True
```

Then inspect snapshot IDs, statuses, polling durations, validation failures, and race winners.

## A completed response was not used

The engine accepts the first valid response, not simply the first completed response.

A completed response may be rejected because it:

- Is empty or contains only interface text
- Does not contain parseable JSON
- Omits required competitor or profile fields
- Uses a generic or non-comparable offering
- Omits one or more threads from a Reddit classification batch
- Quotes evidence that does not occur in the supplied source text
- Fails another task-specific validation rule

Other race participants continue until one succeeds or the stage exhausts its available results.

## Buyer queries are too generic

Set a more specific audit focus:

```python
AUDIT_FOCUS = "specific product, service, audience, or customer need"
```

The notebook rejects known placeholders, but a clear focus still improves search intent, competitor selection, profile scope, and recommendations.

## No valid competitors are found

Competitor validation requires the same buyer, value-chain level, and purchase decision.

Use a more specific `AUDIT_FOCUS` when the target has several unrelated offerings or operates across multiple roles.

Publishers, directories, retailers, marketplaces, distributors, and adjacent suppliers may be visible in the collected sources but are intentionally rejected unless they are genuine substitutes for the target.

## A competitor profile uses fallback data

Profile collection is designed to degrade gracefully. A failed structured profile does not terminate the complete audit.

The fallback preserves the selected competitor's identity and the shared audit scope. Check:

- `04_brand_profiles.json`
- The profile task records under `raw/`
- Debug output for the rejected response and validation reason

## Reddit analysis is partial

The social stage combines native discovery, site-restricted search, existing Reddit URLs, post hydration, comments, and classification. One path may fail while the remaining evidence still produces a usable result.

The report displays a concise completeness warning. Inspect:

```text
05_reddit_social.json
05_reddit_snapshot_manifest.json
```

The social result explains collection and classification warnings. The manifest maps each snapshot to:

- Brand or neutral category
- Operation
- Dataset
- Query or URL scope
- Status
- Race winner or losing-race state

This mapping is the fastest way to understand which snapshot belongs to which part of the audit.

## Reddit returned relevant posts for one company but not another

This can be a real result, but first verify that the cohorts are comparable.

With an explicit focus, the engine chooses one same-type comparison offering for each competitor. Without a focus, it applies the same inferred category to all brands.

Inspect the cohort definitions and queries in `05_reddit_social.json`. Avoid manually comparing a specific target product with a competitor's entire portfolio.

## Reduce Reddit request usage

The default native discovery race width is three snapshots per cohort. To prefer lower usage over latency, set:

```text
REDDIT_NATIVE_RACE_WIDTH=1
```

This does not disable the other discovery paths or classification work.

## Missing measurements display as an em dash

This is expected:

```text
—
```

It means that the value is unavailable or not applicable. For example, a brand with zero search appearances has no meaningful best or average rank.

The corresponding JSON value is `null`.

## A Google AI Mode source uses `google.com/goto`

The notebook attempts to resolve Google redirect URLs and store the final destination.

If a redirect has expired or cannot be resolved, the opaque URL may be excluded from source analysis. This does not invalidate the retained answer text.

## PDF generation fails

Confirm that the dependency installation completed and installed:

```text
markdown
weasyprint
```

If PDF rendering still fails, the notebook records a warning and continues exporting Markdown, JSON, and the ZIP archive.

## The notebook behaves differently after rerunning individual cells

Start a fresh Colab runtime and select:

```text
Runtime -> Run all
```

The notebook contains staged definitions and embedded runtime helpers that must be loaded in order.

## Validate a local setup without using Bright Data requests

Run:

```text
.venv/bin/python scripts/run_local_audit.py \
  --company "Example" \
  --domain "example.com" \
  --country "US" \
  --dry-run
```

This validates local settings and the generated notebook runner without starting a live audit.

## A local run fails

Check the timestamped directory under `local-runs/`.

Useful files include:

- `audit.log`
- Stage JSON files written before the failure
- Raw retained records
- Snapshot manifests

The run directories and `.env.local` are excluded from Git.

## The web interface returns to an empty form

The web wrapper stores an active audit as a server-side job rather than relying only on browser state. Refresh the page and use the same deployed instance; the interface should reconnect to the active job.

If the form remains empty, inspect the service logs for a process restart or redeploy. In-memory job state cannot survive replacement of the running service process unless an external persistent job store is added.

## Run the regression suite

From a configured local environment:

```text
.venv/bin/python -m unittest discover -s tests -q
```

The suite checks social query construction, cohort scope, snapshot diagnostics, notebook embedding, web configuration, and local orchestration behavior.
