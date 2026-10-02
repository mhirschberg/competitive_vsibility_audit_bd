# Service-first audit engine with a generated notebook

Status: design for `feature/service-first-notebook`; no production switch.

Latest checkpoint: `audit_core.audit_models` now owns the Pydantic schemas for
competitor candidates, selected competitors, and brand profiles. The hosted
adapter imports these models directly instead of requiring notebook runtime
bindings, and the notebook builder embeds the same module in its self-contained
core cell. No audit/provider calls or deployment were involved.

Next checkpoint: `audit_core.company_analysis` now owns the provider-neutral
keyword-record normalization (comma-separated strings, legacy query/term
aliases, defaults, trimming, and case-insensitive deduplication). The
standalone notebook embeds this same implementation and removes the duplicate
definition from its legacy analysis cell. Pydantic `CompanyIntake` and
`BuyerIntentKeyword` construction and validation remain an explicit notebook
adapter boundary for now; this extraction does not change AI completion,
placeholder filtering, or schema behavior.

Following checkpoint: the same module now prepares a plain company-intake
payload: legacy flat brand fields, normalized URL/domain, trimmed text, capped
string lists, confidence values, and buyer-keyword records. The notebook keeps
a small adapter that supplies its established URL/list/confidence helpers and
then validates the payload with `CompanyIntake`. This preserves the schema and
the AI-driven completion/placeholder-filtering stages while making input
normalization shared and independently testable.

Schema checkpoint: `audit_core.company_models` owns the Pydantic models for
buyer keywords, brand analysis, and company intake. The notebook builder embeds
that exact source in its core cell in place of duplicate class definitions;
the hosted adapter uses the same importable classes by default while retaining
injection points for tests and transition fixtures. Company-intake payload
preparation and AI completion remain separate from schema validation.

Service detachment checkpoint: `hosted.service_adapter` now supplies
`normalize_company_intake_core` directly to the shared analysis pipeline. The
hosted path no longer requires or calls the notebook's `normalize_company_intake`
runtime binding; the notebook keeps a thin same-named wrapper that calls the
shared normalizer with its embedded Pydantic model. Schema parsing and legacy
model injection tests remain supported.

Keyword completion checkpoint: prompt construction, normalization, filtering
of branded/duplicate results, Pydantic keyword creation, and retention of the
provider record/snapshot ID now live in `audit_core.company_analysis`. Both
the hosted adapter and generated notebook supply only the utility-AI call and
small serialization/parser ports; neither needs the notebook's former
`complete_company_keywords` implementation.

Proofreading checkpoint: its prompt builder, eight-query safety checks,
placeholder/brand/meaning-preservation filters, Pydantic reconstruction, and
applied/rejected/failed result handling now also live in
`audit_core.company_analysis`. The hosted path no longer requires the
notebook's `proofread_buyer_keywords` callback; only utility execution,
JSON parsing/serialization, and target-language selection are supplied as
ports. The generated notebook wraps the same core, with its safety helpers
removed from the legacy cells.

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

Twenty-eighth checkpoint: the service-adapter live canary completed a full
Trello audit on 2026-10-01 with Reddit, Copilot, and measured Google AI Mode
disabled; ChatGPT and Gemini both returned measured answers. The audit took
11m58s, estimated Bright Data usage was $0.087, and the runner's child-process
peak was 245.1 MiB. The run exposed a flat-notebook-namespace collision between
the AI race and source-label constants; the constants were given distinct names
and a regression test was added. All 358 offline unit tests pass (4 optional
integration tests skipped), and the generated notebook is current. This is a
functional canary, not evidence of lower memory: `_build_service_runner_script`
still expands the notebook into a 26,990-line / 739 KiB runner and imports its
legacy dependencies. No push or deployment was made.

The next migration slice is to replace those implicit notebook-global provider
bindings with explicit service adapters, starting with the Bright Data client
and its effective snapshot, SERP, and answer-engine methods. Then extract the
stage-specific provider wrappers (company research, competitor selection,
profiles, Reddit, and report generation) behind the existing `audit_core`
ports. The service runner can become genuinely notebook-free only after all
required bindings have parity fixtures; a fresh live canary and memory
comparison come after that, before any worker-default or deployment decision.

Twenty-ninth checkpoint: `hosted.brightdata_provider.BrightDataProviderClient`
is the first standalone service provider adapter. It composes the existing
Bright Data transport and usage-ledger modules for snapshot trigger/status/
download/polling/scrape, Google/Bing SERP transport, and measured ChatGPT,
Gemini, and Copilot races. Country-compatible payload construction and strict
answer-market validation are retained. Bing Markdown parsing is an explicit
injected dependency; no notebook globals are read. Fake-provider tests cover
usage accounting, race labels, market targeting, and search-health caching.
The full offline suite passes with 363 tests (4 optional integration tests
skipped). This client is not yet wired into `hosted.service_adapter`, and
Google AI Mode research, Reddit, and profile/report provider wrappers are still outstanding.
The legacy notebook runner remains the only end-to-end path for now.

Thirtieth checkpoint: the internal research race is now bound through the
standalone `audit_core.research_race.ResearchProviderAdapter`. Its Bright Data
snapshot and cache operations, prompt localization, task identification,
answer validation, throttling, and error types are explicit dependencies; the
adapter no longer needs notebook globals. The notebook wrapper still installs
the same behavior and keeps old Google-only snapshot checkpoints resumable.
This confirms the architecture distinction: internal research races across
ChatGPT and Gemini; measured Google AI Mode remains a separate audit source.
The generated notebook is refreshed and targeted adapter/builder tests pass.
This adapter is not yet wired into the hosted service runner, so this is not a
memory reduction or a notebook-free hosted execution path.

Thirty-first checkpoint: `hosted.service_adapter` now installs the explicit
research adapter at the client boundary for the opt-in service-coordinator
runner. It uses the existing low-level client's snapshot transport and the
same validation/cache callbacks, but captures them explicitly; the run-only
reuse policy remains dynamic so continuation setup occurs before the first
research call. A saved-response fixture verifies that an invalid ChatGPT
answer falls through to Gemini, resume-only mode makes no replacement calls,
and measured Google AI Mode remains untouched. Seventeen targeted service,
research, and notebook-builder tests pass; no paid calls or deployment were
made. The standalone `BrightDataProviderClient` is still not wired into this
runner, so the service path still initializes legacy notebook definitions and
no memory reduction is claimed.

Thirty-second checkpoint: the opt-in service coordinator now swaps the
notebook-created Bright Data client for `hosted.brightdata_provider.
BrightDataProviderClient` when credentials are present, before preparation
configures the run's usage checkpoint. The standalone client owns snapshots,
SERP access, engine races, and result accounting. The existing measured Google
AI Mode method is rebound to the standalone client, while the internal
research race remains ChatGPT/Gemini and uses the same standalone transport.
A synthetic saved-response test exercises the service-side client swap, race
winner, continuation-only safeguard, and separate Google measurement.
The generated notebook and default worker path are unchanged. Remaining
notebook dependencies include the SERP parser callback and the stage/prompt/
report wrappers, so this is not yet a notebook-free runner or a memory claim.

Thirty-third checkpoint: report generation for the opt-in service runner now
calls `audit_core.report_stage.generate_report_stage_core` directly. Compact
evidence formatting has been extracted to `audit_core.report_evidence`; SERP
metrics, visibility-source collection, market metadata, and locked scope are
explicit inputs. The service path no longer calls the notebook's
`generate_report_stage` wrapper, while the generated notebook keeps its
compatibility wrapper over the same report core. Synthetic coordinator
fixtures now include realistic profile fields and guard against calling the
legacy report function. No provider request or deployment was made; this
reduces one more wrapper dependency but is not yet a notebook-free runner.

Thirty-fourth checkpoint: the service runner now calls
`audit_core.profile_research.run_profile_research_core` directly instead of
the generated notebook's `run_profile_stage` adapter. Profile generation,
snapshot recovery, fallback construction, and root-domain normalization are
explicit ports; the service fixture traps any call to the old wrapper. The
notebook distribution is unchanged. Those lower-level profile provider
callbacks still come from its initialized runtime, so this removes the stage
adapter dependency but does not yet make profile research standalone.

Thirty-fifth checkpoint: profile prompts, response normalization, snapshot
generation/recovery, and fallback construction now live in
`audit_core.profile_provider`. The service binds those functions to the
standalone Bright Data client and explicit model/URL helpers; the generated
notebook embeds the same module and keeps compatibility function names. Offline
tests cover focus-aware prompts, bounded/normalized fields, successful and
pending snapshots, recovery, fallback, and embedding parity. This removes the
profile-provider function dependency on notebook globals; model schemas and
shared runtime helpers are still injected, and no live provider call was made.

Thirty-sixth checkpoint: the opt-in hosted service runner now binds Stage 5
measured AI visibility directly to `audit_core.visibility_stage` and its
standalone Bright Data client. It constructs the neutral prompt through the
shared `audit_core.visibility_prompt` helper and passes the saved Stage 2
Google AI Mode discovery result explicitly. The service no longer requires or
calls the notebook's `run_visibility_stage` wrapper; the notebook adapter and
defaults remain unchanged. Offline fixtures verify provider, options, prompt,
and discovery handoff while guarding against the legacy wrapper. Reddit
collection remains on the existing adapter, and no live provider calls or
deployment were made.

Thirty-seventh checkpoint: `reddit_social.py` now supports explicit per-audit
provider context for the Bright Data client and validated utility-AI race.
Context is propagated into its nested thread pools, so Reddit discovery can
start immediately after competitor selection and continue alongside Stage 5
without sharing or overwriting process-global provider state. The hosted
adapter binds both prefetch and final social collection through that context;
the notebook keeps its historical global fallback and behavior. Offline tests
cover thread propagation, adapter binding, existing Reddit fixtures, and
notebook embedding. The utility-AI race implementation itself still comes
from the existing runner binding; no live calls or deployment were made.

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

Thirty-eighth checkpoint: Reddit's Gemini/ChatGPT utility race now lives in
`audit_core.utility_ai_race` and is shared by the service adapter and generated
notebook. Both requests retain their provider-specific payloads; country is
omitted, only a validator-approved answer wins, returned records remain in the
Bright Data usage ledger, and Reddit's audit metadata is preserved. Offline
tests cover provider failures, invalid answers, payloads, accounting, and the
notebook wrapper. No live request or deployment was made.

Thirty-ninth checkpoint: the hosted service adapter now calls the importable
`reddit_social` module directly for Reddit discovery and collection instead of
requiring those callables from the notebook runtime. The adapter binds the
Bright Data client, utility race, JSON parser, and Google redirect helpers in
context variables propagated into Reddit's thread pool. Service-only transport
imports are stripped from the generated notebook, and both worker image paths
copy the standalone module. Fixture tests can still inject a fake Reddit
module. Other audit stages still load notebook-derived code, so this is not a
notebook-free worker or a memory reduction claim; no paid request or deployment
was made.

Next: continue extracting the remaining provider callbacks used by company and
competitor research and the measured Google AI Mode path. Then remove the
worker's notebook expansion only after all provider/parity fixtures are in
place, followed by a live canary and process-tree memory comparison.

Fortieth checkpoint: research task classification, JSON/narrative answer
validation, and transient-snapshot detection now live in
`audit_core.research_validation`. The service adapter no longer requires the
notebook's corresponding policy callbacks; the generated notebook embeds the
same module source. Existing parser and answer-cleaning utilities remain
explicit dependencies. Fixture coverage verifies task families, minimum
answer quality, JSON requirements, transient records, service wiring, and
notebook-source parity. No provider requests or deployment were made.

Next: extract the remaining research prompt-localization and company-analysis
provider boundary, then wire measured Google AI Mode through the standalone
provider client rather than borrowing the notebook client's bound method.

Forty-first checkpoint: the ChatGPT/Gemini research race now localizes its
prompts through `audit_core.ai_localization` in both service and notebook
paths. Hosted preflight no longer requires the notebook's
`localize_google_ai_prompt` callback; the existing country details, wording,
near-4,096-character handling, cache keys, and true provider labels are
preserved. Fixture tests verify Germany-specific prompt text and notebook
parity. No Bright Data request or deployment was made.

Next: extract the remaining company-analysis provider boundary, then wire
measured Google AI Mode through the standalone provider client rather than
borrowing the notebook client's bound method.

Forty-second checkpoint: company research and response-structuring now run
through `audit_core.company_analysis` in both hosted and notebook orchestration.
It owns the Google AI Mode research call, two-attempt ChatGPT/Gemini JSON
structuring flow, eight-keyword completion gate, keyword proofreading, and
explicit locked-scope result. Existing normalizers and keyword maintenance
helpers remain narrow callbacks. The generated notebook embeds this same core;
the hosted adapter no longer requires `analyze_company_stage`. Fixture tests
cover retry, empty research, keyword completion, scope, and adapter wiring. No
provider request, deployment, or memory reduction claim was made.

Next: connect measured Google AI Mode directly to the standalone provider
client, then continue shrinking the notebook-derived runtime callbacks.

Forty-third checkpoint: measured Google AI Mode now has its own method on
`BrightDataProviderClient`, using the existing Google dataset, country-targeted
payload, requested output fields, timeout, and shared result-accounting
transport. The service adapter no longer copies a bound method from the
notebook-created client. Tests verify the exact request contract, empty-answer
handling, and that the standalone method—not a legacy injected method—is used.
The notebook implementation and its measurement/research separation remain
unchanged. No live provider request or deployment was made.

Next: continue shrinking notebook-derived runtime callbacks and remove the
notebook expansion from the worker only after the remaining provider and stage
boundaries have parity coverage.

Forty-fourth checkpoint: the hosted company-analysis adapter now obtains the
locked target scope directly from `audit_core.competitor_scope`, rather than
requiring the initialized notebook runtime to provide that callback. The
existing service/notebook parity fixtures continue to cover role
classification and scope construction; the adapter test confirms the shared
core is bound and that the notebook callback is no longer required. No provider
request, generated-notebook change, deployment, or memory claim was made.

Next: keep removing correctness-sensitive runtime dependencies where an
existing shared core already has parity coverage, then evaluate the remaining
provider and Stage 2 boundaries before changing worker startup.

Forty-fifth checkpoint: the hosted coordinator now binds Stage 2 through
`audit_core.search_discovery.run_search_discovery_core`, using the saved audit
settings and explicit callbacks for per-query SERP, Google AI Mode questions,
and candidate aggregation. The service runtime no longer requires the
notebook's `run_serp_stage` wrapper when those granular callbacks are present;
a compatibility fallback remains only for reduced transition fixtures. The
shared discovery core already has coverage for bounded first-wave searches,
Google-to-Bing whole-set fallback, disabled Google AI Mode, partial results,
and skipping paid questions after a failed health check. No provider requests,
notebook changes, deployment, or memory claim were made.

Next: extract or directly bind the granular Stage 2 provider callbacks so they
no longer resolve behavior from the notebook runtime, then continue removing
remaining required notebook bindings.

Forty-sixth checkpoint: the standalone Bright Data client now owns the
per-keyword SERP task used by hosted Stage 2. It preserves Google’s single
outer quality retry, Bing’s single attempt, semaphore behavior, result shape,
and immediate stop on Google selector timeouts; the existing lower-level
transport retains its own transient-response retries. Hosted Stage 2 no longer
requires the notebook’s `run_keyword_serp_task` callback. Offline tests cover
retry and timeout behavior and exercise the real provider adapter through the
shared discovery core. No paid request, notebook change, deployment, or memory
claim was made.

Next: remove remaining notebook-derived serialization and presentation
callbacks where the shared engine already has equivalent behavior, while
keeping report artifacts and the notebook's user-facing flow unchanged.

Forty-seventh checkpoint: hosted orchestration now binds audit-record
assembly, report filenames, Bright Data usage copy, storage cleanup, and
JSON/text/ZIP artifact writers directly from shared `audit_core` modules.
These are no longer required callbacks from the notebook runtime; a complete
offline hosted-pipeline fixture runs with those bindings removed. Existing
notebook generation continues embedding the same shared implementations.
The report output contract remains the structured shared audit record and
standard dated artifact names. No provider requests, deployment, or memory
claim was made.

Next: extract the remaining engine-result/profile-task serializers and reduce
the progress-display callbacks that are still sourced from notebook runtime.

Forty-eighth checkpoint: engine-result and profile-task serialization now
live in shared `audit_core.report_export`; elapsed-time formatting lives in
`audit_core.primitives`. Hosted orchestration no longer requires these three
notebook callbacks, and an end-to-end offline adapter fixture runs with them
removed. Serializer tests verify that large HTML/screenshot fields remain
excluded while measured records and profile fields are preserved. The
notebook's existing output formatting remains compatible. Console printing
callbacks remain adapter-owned because they are presentation, not audit
logic. No provider requests, deployment, or memory claim was made.

Next: review the remaining notebook-derived callbacks as adapter boundaries;
only move console output if a shared presentation interface preserves the
notebook and hosted UI behavior without coupling the core to either UI.

Forty-ninth checkpoint: hosted reporting now calls the shared source-appendix
finalizer directly and binds Reddit warning/section formatting from the same
`reddit_social` module used by the notebook. The hosted runtime no longer
requires notebook callbacks for `finalize_report`, Reddit section insertion,
or Reddit warning summarization. A social-on/off offline adapter fixture
passes with all three removed. Console progress callbacks remain explicit
presentation ports. No provider requests, generated-notebook changes,
deployment, or memory claim was made.

Next: inventory the remaining runtime callbacks and separate genuine provider
or UI ports from duplicated engine logic before removing any more bindings.

Fiftieth checkpoint: URL-domain normalization, locked-scope restoration,
resume-directory discovery, audit slugs, and export-prefix generation are now
bound from shared core modules instead of the notebook runtime. Resume lookup
is explicitly scoped to the runner's base directory. Official-site HTTP
verification remains an explicit port because it performs external network
I/O; provider credentials, model constructors, and UI callbacks also remain
ports. Offline end-to-end tests pass with the removed helpers absent. No
provider requests, deployment, or memory claim was made.

Next: inspect the remaining bindings for other pure helpers with existing
shared sources, while preserving deliberate provider, persistence, and UI
boundaries.

Fifty-first checkpoint: visible-URL extraction, public URL normalization,
and hostname cleanup now live in `audit_core.domains` and are used directly
by hosted profile preparation. The notebook builder removes only shadowed
copies, preserving its generated shared functions across repeated builds; a
regression test covers that idempotence. URL edge cases and the offline hosted
pipeline pass. The JSON parser remains an explicit binding for now: inspection
found two notebook implementations with different recovery behavior, so they
need parity tests before consolidation. No provider requests, deployment, or
memory claim was made.

Next: characterize both JSON-parser variants against captured fixture cases,
then decide whether one shared parser can safely replace the runtime callback.

Fifty-second checkpoint: AI JSON cleaning and parsing now live in
`audit_core.json_parsing`, and hosted provider flows use that implementation
directly rather than requiring a notebook `parse_ai_json` callback. The more
capable prior behavior is preserved: fenced and surrounding text, escaped
Markdown delimiters, repairable JSON, first-object recovery from arrays, and
diagnostic previews on failure. Notebook generation embeds the same module
and removes shadowed parser copies. Parser, adapter, and notebook parity tests
pass. No provider requests, deployment, or memory claim was made.

Next: inventory the remaining runtime dependencies and identify the next
shared policy/normalization helpers that can be moved without crossing
provider or UI boundaries.

Fifty-third checkpoint: AI-interface cleanup and Markdown report unwrapping now
live in `audit_core.text_cleaning`. Hosted research validation and report
finalization call the shared implementation directly, so the service no longer
depends on a notebook-defined cleaner. Notebook generation embeds the same
source and removes shadowed copies. Focused parity checks and the full offline
suite pass (424 tests, 4 skipped); the notebook build and no-provider-call dry
run pass. No paid requests or deployment were made, and this extraction alone
is not a memory-reduction claim.

Next: continue the runtime-binding inventory, looking for another pure helper
whose ownership can move without crossing provider, persistence, or UI
boundaries.

Fifty-fourth checkpoint: opaque Google `/goto` URL recognition now lives in
`audit_core.domains` and is bound directly by the service. The redirect resolver
remains a caller-supplied network operation. Notebook generation embeds the
shared predicate and removes the old duplicate. Service preflight no longer
requires the notebook-defined URL predicate or the already-shared AI text
cleaner. All 425 tests pass (4 skipped); the notebook is current and the dry
run made no Bright Data requests. No deployment or memory-reduction claim was
made.

Next: continue auditing the remaining notebook-supplied policy and domain
callbacks; keep network resolution, report rendering, persistence, and UI
callbacks at their existing adapter boundaries.

Fifty-fifth checkpoint: model serialization now lives in the shared
`audit_core.primitives.model_to_dict` helper, and the hosted adapter no longer
requires a notebook-provided serializer. The helper preserves native Pydantic
v1/v2 behavior and supports plain record objects used by fixtures. Notebook
generation embeds that same helper and drops the old definition idempotently.
The full suite passes (426 tests, 4 skipped); generated notebook and no-paid-
request dry run checks pass. No deployment or memory-reduction claim was made.

Next: inspect remaining service callbacks, prioritizing policy/normalization
logic while retaining network, persistence, and presentation at the edges.

Fifty-sixth checkpoint: selecting the most relevant company-research excerpts
now lives in `audit_core.company_analysis` and is used directly by the hosted
service. The notebook embeds that same provider module and no longer keeps a
second selector implementation. Output matched the previous notebook helper
on four captured-style fixtures, including long research with all eight buyer
queries. The full suite passes (426 tests, 4 skipped); notebook generation and
the no-provider-call dry run pass. No paid requests, deployment, or memory
reduction claim was made.

Next: continue the runtime-boundary review, focusing on remaining company
normalization and competitor-scope helpers without moving model or provider
calls into pure core code.

Fifty-seventh checkpoint: locked-scope brand-family normalization and
country-domain scoring now live in `audit_core.competitor_scope`. The hosted
adapter constructs `CompetitorDecisionPorts` from shared logic instead of
requiring three notebook callbacks; the notebook uses the same functions and
its shadowing copies are removed. Tests cover common country suffixes and
verify service/notebook parity. Full suite: 428 passed, 4 skipped; notebook
check and no-provider-call dry run pass. No deployment or memory-reduction
claim was made.

Next: review company intake normalization and keyword-record normalization;
keep Pydantic construction and any AI-powered completion/proofreading behind
explicit ports.

Fifty-eighth checkpoint: hosted company analysis now uses the shared,
validator-backed Gemini/ChatGPT utility race directly for structuring, keyword
completion, and proofreading. The service adapter no longer requires the
legacy notebook `run_chatgpt_without_web` callback; Reddit and company analysis
share the same explicitly constructed provider adapter. The generated
notebook path is unchanged and continues calling its compatibility wrapper.
Offline adapter coverage verifies the utility port and absence of the legacy
runtime binding. No provider request, notebook change, deployment, or memory
reduction claim was made.

Next: inspect the remaining company-stage runtime bindings and classify each
as shared policy, provider operation, persistence, model validation, or UI
output before removing another dependency.

Fifty-ninth checkpoint: the hosted company stage now binds `CompanyIntake`,
`BrandAnalysis`, and `BuyerIntentKeyword` from the shared service schemas rather
than optionally inheriting notebook runtime classes. Keyword completion and
proofreading likewise use the shared keyword schema directly. These are
provider-neutral model contracts, not per-run provider or UI settings; the
notebook still embeds and uses the same schema source. Offline adapter tests
verify the hosted path works when the legacy model bindings are absent. No
provider request, notebook change, deployment, or memory-reduction claim was
made.

Next: review the remaining Stage 1 provider and persistence ports for redundant
runtime callbacks, keeping Bright Data operations and filesystem writes
explicit at the adapter boundary.

Sixtieth checkpoint: company research excerpt selection is now called directly
inside `audit_core.company_analysis`; it is no longer an injected callback to
the prompt builder or analysis ports. Both the service and generated notebook
therefore use the same deterministic selection policy without adapter wiring.
The notebook builder still removes the shadowed duplicate implementation.
Company prompt fixtures and notebook generation checks cover the shared path.
No provider requests, deployment, or memory-reduction claim was made.

Next: inspect whether the company-stage JSON parser is still a meaningful
boundary now that both service and notebook resolve to the same shared parser;
retain it as a port only if it continues to provide useful test or format
variation coverage.

Sixty-first checkpoint: company-stage analysis, keyword completion, and
proofreading now call the shared JSON parser directly instead of carrying a
parser callback through `CompanyAnalysisPorts` and helper calls. This is safe
because the notebook and hosted adapters already use the same parser; malformed
or fenced JSON still follows its existing recovery behavior. A fenced-JSON
company fixture checks this end to end, and the generated notebook embeds the
same code. No provider requests, deployment, or memory-reduction claim was
made.

Next: review `normalize_intake` and `build_locked_scope` as the remaining
company-analysis ports; retain them only where notebook compatibility or
cross-module ownership still warrants explicit injection.

Sixty-second checkpoint: company intake validation now calls the shared schema
normalizer directly, and locked-scope creation calls the shared
`competitor_scope` policy directly. Neither helper is passed through
`CompanyAnalysisPorts` anymore; provider calls, output writing, and the
notebook's compatibility wrapper remain at their respective boundaries. An
offline suffix-list fixture keeps domain normalization deterministic. Service
and notebook tests pass after regenerating the shared cell. No paid requests,
deployment, or memory-reduction claim was made.

Next: inspect whether the company analysis stage still needs a custom
`error_type` port, or whether it can depend on the shared provider error type
without changing the notebook's failure messages.

Sixty-third checkpoint: company-analysis failures now raise the shared
`BrightDataAPIError` directly instead of carrying a configurable exception
class through `CompanyAnalysisPorts`. The hosted service imports that class
from the standalone transport module; in the generated notebook, the service-
only import is stripped and the core resolves the same class defined by the
embedded transport cell. The no-research failure fixture confirms the existing
exception base and user-facing message. No provider requests, deployment, or
memory-reduction claim was made.

Next: audit other remaining service-adapter runtime bindings for duplicated
provider error classes, but change them only where class identity and caller
handling are demonstrably equivalent.

Sixty-fourth checkpoint: the hosted adapter no longer requests a
notebook-created `BrightDataAPIError` class. Research and competitor operations
use the same shared provider error class as the standalone Bright Data client.
Search and profile recovery likewise use the provider module's
`SnapshotTimeoutError`, so pending-snapshot handling catches the exception
actually raised by that client. The distinct research-race timeout remains an
explicit port because it carries a list of snapshot IDs and has its own
caller-facing message. Offline service, Google-timeout, and competitor-scope
tests pass without either legacy error-class binding. No provider requests,
deployment, or memory-reduction claim was made.

Next: inventory any remaining runtime class/factory dependencies at the
service boundary, separating true output-model adapters from notebook copies
of shared schemas.

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
