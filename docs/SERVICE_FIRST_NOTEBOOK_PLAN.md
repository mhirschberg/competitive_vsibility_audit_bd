# Service-first audit engine with a generated notebook

Status: design for `feature/service-first-notebook`; no production switch.

First checkpoint: the runner builder now lives in `runner_builder.py`, and the
worker imports it without loading `app.py` or Gradio. The old app re-exports
the same functions during migration. A representative generated runner was
byte-for-byte identical before and after extraction. This is not yet a
measured production-memory reduction; the container still installs Gradio.

Second checkpoint: `audit_core.primitives` is importable service-side code and
is embedded into the self-contained notebook by `scripts/build_notebook.py`.
That builder also synchronizes the existing Reddit and research provider
sources without touching unrelated notebook cells. Run
`python scripts/build_notebook.py --check` before committing, or `--write` to
refresh generated cells. Most audit stages still live in the notebook; the
hosted worker has not switched to a service-native audit runner.

Third checkpoint: locked market-scope construction, role classification, and
ranking of eligible direct competitors now live in
`audit_core.competitor_scope`. The notebook embeds the same source; a small
service-only relative import is removed during bundling because its primitive
dependency was embedded in an earlier cell. Fixture parity covers KEBA and
Apple/Samsung/Google smartphone scopes, plus rejection and stable ranking.
At that checkpoint, candidate discovery and AI validation still depended on
the notebook runtime.

Fourth checkpoint: `audit_core.competitor_research` now owns the candidate
discovery/validation orchestration, bounded parallel batch, consistency retry,
and selection-score calculation. It receives a `query_json(prompt)` port;
the notebook supplies the Bright Data implementation in a small adapter. A
synthetic saved-answer fixture replays success, retry, rejection, and provider
failure through both the importable module and bundled notebook code. No paid
provider calls are needed for these regression tests. Prompt construction,
answer normalization, and candidate-universe building still reside in the
notebook and are the next extraction targets. This fixture is deliberately
labelled synthetic; it is not a captured production response.

Fifth checkpoint: the seven remaining competitor-decision helpers now live in
`audit_core.competitor_decisions`: strict verdict canonicalization, shortlist
construction, discovery/validation/retry prompts, retry eligibility, and final
verdict normalization. Notebook wrappers pass URL, domain, and country helpers
through `CompetitorDecisionPorts`; the generated notebook embeds the same
module. The seven extracted function bodies were AST-compared with the prior
notebook commit after accounting for only the new explicit port aliases and a
renamed internal call. The hosted runner still executes the generated notebook;
this does not yet switch production to a service-native runner.

Sixth checkpoint: the Stage 3 selection decisions now live in
`audit_core.competitor_stage`. It accepts explicit provider, checkpoint, and
model ports; the notebook wrapper supplies its existing Bright Data functions
and embeds the same stage code. Synthetic saved-result tests cover two selected
competitors, rejected candidates, resume without new requests, provider
failure semantics, and service/notebook parity. Provider adapters for this
stage still live in the notebook, and the hosted worker still runs the
generated notebook. This is a shared, importable *stage core*, not yet a
complete service-native runner. No live provider call or production deployment
was made at this checkpoint.

Seventh checkpoint: `audit_core.competitor_pipeline` now assembles discovery,
candidate validation, bounded batch work, checkpoint serialization, and raw
evidence persistence. The notebook's Stage 3 passes its existing Bright Data
client, parser, decision helpers, and output directory into that importable
pipeline; the former notebook-only adapter functions were removed. Saved-answer
tests compare service and bundled pipeline behavior without paid calls. The
Bright Data client itself, the other audit stages, and the top-level audit
orchestrator still live in the notebook, so the hosted worker remains on the
current runner until those pieces are migrated and checked end to end.

Eighth checkpoint: the result-based Bright Data usage ledger now lives in
`audit_core.brightdata_usage`, and the effective snapshot HTTP transport plus
polling live in `audit_core.brightdata_transport`. The notebook embeds both
sources and its client inherits the ledger; status, download, trigger, scrape,
and wait operations use the shared transport functions. Fake-response tests
cover NDJSON, transient empty downloads, materializing snapshots, result-based
cost estimates, and checkpoint restore. The class still has later notebook
overrides for SERP and answer-engine behavior. Those overrides must be mapped
and extracted before an imported service client would be equivalent to the
notebook's effective client. No live requests or production change were made.

Ninth checkpoint: `audit_core.serp_transport` owns the effective SERP request,
retry, parsing dispatch, and quality check; `audit_core.serp_selection` owns the
Google/Bing health-check decision and one-use result cache. The notebook embeds
these sources and keeps thin client methods for its existing configuration and
progress state. `audit_core.research_race` owns the ChatGPT/Gemini research
snapshot race, including resume-only behavior and the winning provider label;
`research_fallback.py` supplies the current provider adapters. Fake-response
tests cover empty SERP responses, selector timeouts, Bing fallback, explicit
Google selection, caching, and notebook state synchronization. The remaining
SERP parsers, measured AI-answer engine races, report stages, and top-level
orchestration still live in notebook cells; this checkpoint is not a complete
service-native client. No live provider request or production deployment was
made.

Tenth checkpoint: `audit_core.ai_visibility_race` now owns the measured
ChatGPT/Gemini/Copilot snapshot race. It keeps the real engine label, winning
snapshot, citations, retry-on-transient-trigger behavior, and result-based
accounting. The notebook's client retains a thin adapter so the existing
country-payload and localization wrappers continue to apply. The parsed-light
organic-result normalizer now lives in `audit_core.serp_parsing`, also embedded
in the notebook. Synthetic tests cover measured-answer labels, Copilot cited
sources, failed snapshots, nested Google result shapes, and adapter parity.
The strict and fallback Markdown SERP parsers, country/localization rules, and
the complete service-native runner remain future work. This checkpoint made
no live Bright Data request and did not change the hosted deployment.

Eleventh checkpoint: `audit_core.serp_markdown` now owns both strict Google
and Bing Markdown parsers plus the effective Google generic fallback. It takes
URL/domain/redirect helpers through explicit ports and records fallback
diagnostics in the adapter's dictionary. The notebook embeds the same source;
its existing parser names are thin compatibility adapters. Synthetic tests
cover organic ranking, rich-result and navigation exclusion, Bing tracking URL
decoding, Google fallback, redirect avoidance when a direct URL is nearby, and
service/notebook parity. The fallback now also decodes an absolute
`https://www.google.com/url?...` redirect, not only relative `/url?...` links.
Bing remains conservative: an unusable strict result is reported as empty, not
invented from unrelated links. No live provider request or production change
was made. Country/localization rules, report stages, and the complete
service-native runner remain to be extracted.

Twelfth checkpoint: `audit_core.ai_localization` now owns the country aliases,
market-language table, Gemini prompt-only transport exceptions, localized
prompt instructions, payload country handling, answer-country assessment, and
bounded retry of measured AI answers. The notebook embeds this source and
retains thin adapters to its current settings and client. Synthetic tests cover
US/DE/GB acknowledgement, explicitly wrong scraper-country metadata, retry
then success, two failed attempts, Gemini DE prompt-only versus US field
targeting, utility requests without a country, and composed notebook adapter
metadata. Missing or contradictory market evidence is not recorded as a
successful measured answer. The near-limit 4096-character research-prompt
fallback is preserved, not redesigned here. No live provider call or hosted
deployment was made. Report stages and the full service-native orchestrator
remain to be extracted.

Thirteenth checkpoint: `audit_core.report_content` now owns the deterministic
Markdown report text and its final cosmetic polish. Country, traditional-search
engine/status, and observed-source collection are explicit inputs rather than
ambient notebook globals. `audit_core.report_stage` calculates report metrics,
builds evidence and generator metadata, and returns the existing stage result
without an AI call. The notebook embeds both modules and retains small adapters
for its current globals and `LAST_UTILITY_REPORT_RESULT`. A captured pre-move
report fixture matches the extracted output byte-for-byte; synthetic tests
cover notebook/service parity, unavailable-search wording, evidence fallback,
and legacy notebook state. No live provider calls or hosted deployment were
made. PDF rendering, Reddit report insertion, other audit stages, and the
top-level service-native orchestrator still remain in notebook runtime code.

Fourteenth checkpoint: `audit_core.report_export` now owns the observed-source
appendix, final report assembly, result-based Bright Data cost section, record
cleanup, and construction of the structured audit JSON object. The notebook
embeds the module; its existing `finalize_report` adapter supplies the current
source collector and boilerplate cleaner, and the top-level notebook runner
passes its measured stage results into `build_audit_record`. Synthetic tests
cover source-appendix idempotence, lower-bound cost wording, retained engine
labels, and the audit object schema. This stage does not write files or call
providers. File writing and locked-scope augmentation were later extracted in
the seventeenth checkpoint. PDF rendering, Reddit insertion, and the top-level
orchestration remain notebook-owned. No live requests, production deployment,
or cost incurred.

Fifteenth checkpoint: `audit_core.domains` now owns registrable-domain
normalization, `audit_core.serp_metrics` owns traditional-search visibility
metrics, and `audit_core.brand_mentions` owns conservative brand-mention
detection. `audit_core.visibility_stage` orchestrates the selected measured AI
answers and Google AI Mode coverage, receiving the Bright Data client, prompt
builder, and discovery sample as explicit inputs. The generated notebook
embeds these modules and keeps a thin adapter for its current globals.
Synthetic tests cover company/domain matching, partial and failed answers,
per-engine wait settings, and service/notebook parity. The top-level audit
orchestrator, provider adapters, social stages, PDF rendering, and artifact
writing are still notebook-owned; the hosted worker has not switched to a
service-native runner. No live provider call or production deployment was
made at this checkpoint.

Sixteenth checkpoint: `audit_core.visibility_prompt` now builds the neutral
category-level AI question with an explicit audit focus, while
`audit_core.visibility_sources` classifies, deduplicates, and quality-filters
citations with optional Google redirect-resolution ports. Canonical citation
URL handling now shares `audit_core.domains` with root-domain normalization.
The notebook embeds these modules and preserves its existing settings and
redirect adapters. A saved synthetic citation fixture covers source classes,
cross-engine deduplication, unresolved Google-interface links, and
service/notebook parity; the base prompt and source outputs were also compared
against the preceding notebook commit. This still does not provide a complete
service-native Bright Data client or top-level runner. No paid request or
production deployment was made.

Seventeenth checkpoint: `audit_core.artifact_writes` now owns JSON/text output,
ZIP assembly, and the locked-scope augmentation formerly duplicated in a late
notebook override. `audit_core.artifact_resume` selects a matching incomplete
audit or restores its checkpoint ZIP. The notebook embeds both modules and
keeps only a settings adapter for the locked-scope write. Tests cover old and
dated report names, archive contents, unsafe ZIP members, resumed checkpoints,
and notebook/service parity. The dated final JSON now retains locked-scope
metadata, which the old exact-name condition silently missed. PDF rendering,
social insertion, the remaining provider adapters, and top-level orchestration
are still notebook-owned. No live request or production deployment was made.

Eighteenth checkpoint: the first top-level audit stage now lives in
`audit_core.company_stage`. It handles a fresh company/keyword analysis or
restores Stage 1 from an existing checkpoint, normalizes the official target
domain, keeps locked scope synchronized for scoped JSON writes, and persists
the company and raw-response records. The notebook's main function now calls
this importable stage through explicit provider, model, scope, writer, and
progress ports. Synthetic tests cover fresh and resumed runs, including no
new provider call on resume; the generated standalone runner compiles. Later
stages and the top-level scheduler still execute through notebook code. No
paid provider request or production deployment was made.

Nineteenth checkpoint: `audit_core.search_discovery` now owns the effective
Stage 2 search and Google AI Mode discovery flow, including partial search
coverage and whole-set Google-to-Bing fallback without mixed rankings.
`audit_core.search_stage` owns the Stage 2 checkpoint and progress handling.
The checkpoint now retains measured AI Mode discovery and restores it on
resume, instead of losing those results; older checkpoints without that field
remain resumable. The notebook embeds both modules and keeps a thin provider
adapter. Synthetic tests cover fallback, partial results, fresh checkpoints,
and resume without new provider calls. Later stages and the top-level
scheduler remain notebook-driven. No paid provider request or production
deployment was made.

Twentieth checkpoint: `audit_core.competitor_selection_stage` now owns Stage 3
orchestration around the already shared competitor-selection engine. It records
selected and rejected candidates, preserves continuation warnings and the
Google AI snapshot-cache transition, and starts optional Reddit discovery
only after selection artifacts are saved. The notebook keeps a thin adapter
for provider calls, progress output, and files. Synthetic tests cover fresh
and continued runs, artifact contents, warning propagation, social-prefetch
ordering, and notebook adapter wiring. Profile, visibility, social, and report
orchestration still need migration before the hosted job can use a fully
service-native runner. No paid provider request or production deployment was
made.

Twenty-first checkpoint: `audit_core.profile_research` now owns the Stage 4
parallel profile jobs, recovery of late provider snapshots, fallbacks, and
role/domain deduplication through explicit provider ports.
`audit_core.profile_stage` owns the profile artifact, duration, and warnings;
the target's official domain and URL are restored before writing the artifact.
The notebook embeds both modules and retains thin provider and progress
adapters. Synthetic tests cover pending recovery, fallback counts, deduped
profiles, artifact contents, and adapter wiring. Continuation behavior is
unchanged: Stage 4 is recalculated rather than loaded from its prior artifact.
Later stages and the top-level scheduler remain notebook-driven. No paid
provider request or production deployment was made.

Twenty-second checkpoint: `audit_core.visibility_checkpoint_stage` now owns
Stage 5 orchestration around the previously shared visibility measurement.
It starts optional Reddit work concurrently, records successful and failed
AI engines without turning unavailable answers into zero scores, and saves the
measured visibility artifact before Stage 6 waits for social results. The
notebook retains a thin provider/progress adapter. Synthetic tests cover
partial engine failure, checkpoint contents, parallel Reddit timing, and
adapter wiring. Reddit completion/reporting and final report orchestration
remain notebook-driven. No paid provider request or production deployment was
made.

Twenty-third checkpoint: `audit_core.social_completion_stage` now owns the
optional Stage 6 Reddit completion, concise progress/warning messages, and
both social-result and snapshot-manifest artifacts. The disabled path still
writes explicit empty social artifacts without a Reddit stage banner. The
notebook embeds this module and retains only provider/progress adapters.
Synthetic tests cover disabled, competitive partial, and legacy sample paths,
plus the notebook adapter. Final report orchestration and the top-level
scheduler remain notebook-driven. No paid provider request or production
deployment was made.

Twenty-fourth checkpoint: `audit_core.report_render_stage` now owns the final
report narrative, Reddit and Bright Data usage sections, domain-correction
note, Markdown/PDF export, and raw research record. A PDF failure remains a
warning rather than discarding Markdown or usage data.
`audit_core.audit_finalize_stage` assembles the structured audit JSON and ZIP
file manifest through explicit ports. While wiring this final stage, an
integration gap from the Stage 3 extraction was found and fixed: the full
competitor selection result is again passed to `build_audit_record`, not only
the selected competitors. Synthetic tests now cover that handoff, successful
and failed PDF rendering, result-based cost data, and JSON/ZIP paths. The
individual stages are importable, but the top-level scheduler and hosted job
switch still need migration and end-to-end parity checks. No paid provider
request or production deployment was made.

Twenty-fifth checkpoint: `audit_core.audit_pipeline` is an importable,
notebook-free coordinator for all audit stages. It accepts a prepared run
context and explicit provider, artifact, progress, and finalization ports; it
does not import Colab, the notebook, or the web app. An offline fixture now
runs the complete service coordinator and the generated notebook's top-level
function with the same provider answers, both with Reddit disabled and
enabled. The normalized final record matches across the two paths for
selected competitors, search results, AI visibility, Reddit status, Bright
Data usage, warnings, and stage names; the service path also writes all
expected artifacts. Real Bright Data/provider adapters, run preparation, and
a hosted worker switch remain separate work.
No paid provider request or production deployment was made.

Twenty-sixth checkpoint: `audit_core.audit_preparation` now handles the
pre-stage setup through explicit ports: resolve a redirecting official site,
select a fresh directory or the latest compatible checkpoint, preserve the
original run timestamp on resume, create the raw directory, and configure
usage and Google AI snapshot caches. Fresh runs save the canonical settings;
resumed runs can import recovery snapshot IDs and still warn about legacy
checkpoints. The generated notebook calls this module with `/content` as its
output root, while a hosted adapter can supply its own root. Offline tests
cover fresh redirects, resume, legacy warnings, cache flags, and failure
before any run files are created. The hosted adapter and live parity check
remain future work; no paid request or production deployment was made.

Twenty-seventh checkpoint: `hosted.service_adapter` binds the existing
Bright Data, search, social, report, and artifact functions to the importable
preparation and pipeline modules. It passes the measured search status and
Google AI discovery result into later stages and resolves the report generator
only at finalization. The Cloud Run worker can select this path with
`AUDIT_ENGINE_MODE=service_adapter`; the default remains `notebook`, so no
deployed behavior changes. Offline fixtures compare both paths with Reddit
on and off and verify that missing bindings fail before any provider work.
This adapter still loads the legacy notebook definitions and therefore is a
compatibility bridge, not yet the expected memory reduction. A live canary,
memory measurement, and removal of those definitions remain future work.

Export naming: user-facing PDF, Markdown, JSON, and ZIP files now start with
the original UTC run timestamp, company, optional focus, and country. The
notebook embeds the shared `audit_core.artifact_names` source; hosted artifact
discovery recognizes both new and legacy report names. Published Reddit data
and run logs receive the same display prefix. Internal numbered checkpoints
retain their established names so resume/replay remains compatible. A resumed
run derives its export prefix from the saved original timestamp, and completed
new-named reports are excluded from resume discovery. This naming change was
verified without paid provider requests or a hosted deployment.

Date correction: the discovery prompt no longer contains the workshop date
September 15, 2026. A new run records its UTC start date in the locked scope;
a resumed run restores the saved scope and original run date. Older checkpoints
without the date are backfilled from their `created_at` timestamp. This avoids
re-dating a continued audit to the day it was resumed.

## Decision

The service implementation becomes the source of truth. The Colab notebook is a
generated, self-contained distribution of the same audit engine, not a second
implementation and not a thin link that imports mutable code from `main` at
runtime. Users keep the current notebook experience: enter their own Bright
Data credentials, run the cells, inspect the method, and download the same
report artifacts.

This refactor is for maintainability, testability, and measurable resource
control. Moving identical Python statements from `.ipynb` to `.py` is **not**
assumed to reduce memory by itself. The hosted worker already compiles notebook
cells into a regular Python script and runs that script outside Jupyter.

## Proposed boundaries

```text
Browser / API / organizer controls
             |
             v
       Hosted job adapter --------> durable audit state and report storage
             |
             v
      audit_core.run(settings, ports)
         |       |        |
         |       |        +-- progress / checkpoint / artifact ports
         |       +----------- Bright Data search, answer, social ports
         +------------------- pure selection, validation, scoring, reporting

Generated Colab notebook
  = install/configure cells + the same audit_core modules + notebook adapter
```

`audit_core` must not import Gradio, Firebase, Supabase, Cloud Run, or Colab.
The hosted and notebook adapters own authentication, storage, progress display,
and output location. Both use the same settings schema, prompts, scope rules,
source labels, report builder, and Bright Data accounting.

## Migration order

1. Capture baseline behavior and peak resident memory by stage for a small,
   medium, and social-enabled audit. Record process-tree memory (worker parent
   plus runner child), not just the child process. No live requests are needed
   for deterministic fixture tests.
2. **Done in this branch:** Extract the runner builder from `app.py` into a
   lightweight module so the hosted worker no longer imports Gradio. Keep the
   current notebook-based runner and public behavior unchanged. Measure this
   small change separately in the deployed container before lowering memory.
3. Extract pure settings, prompt, validation, competitor-scope, scoring, and
   report-building code into `audit_core`. Move one stage at a time, retaining
   the old execution path until fixture parity passes.
4. Put external operations behind narrow interfaces. Keep existing bounded
   races, retry limits, snapshot checkpoints, partial-coverage reporting, and
   explicit `unavailable` states. Do not synthesize a measured answer from a
   different provider.
5. Switch the hosted job to a minimal CLI runner using `audit_core`; leave the
   current runner available as a rollback path during verification.
6. Generate the checked-in notebook from the same module sources. The build
   writes complete code into tagged cells so Colab needs no server checkout or
   runtime GitHub import. A check command fails if the committed notebook is
   stale relative to the engine.
7. Compare the hosted runner and generated notebook on identical fixtures and
   one opt-in live audit. Compare normalized report JSON, selected competitors,
   source availability, usage counters, and report artifacts. Only then switch
   the default hosted path.

## Acceptance criteria

- Existing hosted UI, login, quota, email, history, and purge behavior remain
  unchanged; this branch initially changes only worker/engine internals.
- A user can run the generated notebook with only the documented Bright Data
  setup and obtain the same audit decisions and report content as the service
  for the same captured provider responses.
- Every answer-engine measurement retains its true provider label. Missing
  sources remain missing, not replaced by model-generated approximations.
- Peak process-tree memory and elapsed time are measured before and after;
  lower Cloud Run memory allocation is proposed only after repeated runs fit
  with headroom.
- The current `main` deployment remains untouched until the branch passes
  parity tests, live smoke tests, and an explicit deployment decision.

## Risks to test early

- Generated notebooks can drift unless generation is deterministic and checked
  in CI.
- Module imports, async entry points, and paths differ between Colab and a
  container; both environments need dedicated smoke tests.
- PDF byte-for-byte equality is not a useful parity target because rendering
  metadata may vary. Compare structured report content and verify both PDFs
  render and contain the required sections.
- Worker idle time waiting for external snapshots may cost more than resident
  memory. Event-driven suspension is a later architecture change, not a
  prerequisite for extracting the engine.
