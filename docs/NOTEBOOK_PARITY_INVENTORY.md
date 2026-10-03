# Notebook and hosted-engine parity inventory

This inventory is a read-only review of the current service-first branch. It
identifies where notebook and hosted execution already share implementation,
where separate adapters are intentional, and where the next parity work has
the best payoff. It does not claim live-provider equivalence.

## Current boundaries

| Area | Notebook path | Hosted path | Assessment and evidence |
| --- | --- | --- | --- |
| User setup and access | `competitive_visibility_audit_bd.ipynb` cells `UsMNZ4-2jKg6` (configuration) and `final-run` | `web/` configuration plus `hosted/api.py`, `hosted/worker.py` | Intentionally different. Google login, quotas, workshop access, history, and admin controls are web-only. The audit-settings payload is the contract to compare; these features should not be copied into the notebook. |
| Audit stage implementations | Embedded sources generated into notebook cells `final-core`, `final-analysis`, `final-orchestration`, `runtime-utilities-merged`, and `research-provider-race` | Importable `audit_core/` modules called through `hosted/service_adapter.py` | Largely shared. `notebook_builder.py` embeds source files, including models, transport/parsing, company analysis, search, competitor decisions, profiles, visibility, Reddit completion, reporting, and finalization. Notebook-side adapters preserve Colab callbacks and globals. |
| Whole-audit sequencing | `run_competitive_visibility_audit` in `final-orchestration` is now a thin Colab adapter; the generated notebook embeds `audit_core.audit_pipeline.run_audit_pipeline` | `run_audit_pipeline` in `audit_core/audit_pipeline.py`, prepared by `hosted/service_adapter.py` | Coordinator is shared. Notebook-specific preparation, ports, progress state, and output globals remain in its adapter. Obsolete per-stage call templates and their marker constants have been removed from the builder; their former tests were replaced by whole-pipeline notebook/service fixtures. |
| Company/search/competitor/profile/visibility/report stages | Shared `*_stage_core` functions embedded into the notebook, with provider/UI adapters | Same `audit_core` stage functions with service adapters/ports | Shared decisions with different I/O bindings. Targeted coverage includes `tests/test_company_stage.py`, `test_search_stage.py`, `test_competitor_selection_stage.py`, `test_profile_stage.py`, `test_visibility_stage.py`, `test_report_stage.py`, and `test_social_completion_stage.py`. |
| Research and answer-engine calls | Shared race/validation/prompt modules embedded by `notebook_builder.py`; notebook provider callbacks | Shared core plus Bright Data/provider adapters in `hosted/service_adapter.py` and `hosted/brightdata_provider.py` | Provider-neutral race policy is shared; credentials, request transport, logs, snapshot persistence, and network resolution are adapter responsibilities. Live provider behavior is not proven equivalent by offline fixtures. |
| Reddit collection | `reddit_social.py` embedded into the standalone notebook | `hosted/service_adapter.py` imports the same `reddit_social.py` module | Core collection/analysis source is shared. Scheduling and stage integration use shared stage cores. Parity currently has a synthetic Reddit-enabled whole-audit fixture; live Reddit parity has not been run as a notebook-vs-service comparison. |
| Report content and artifacts | Shared report content/export modules; notebook-bound file destination and PDF callback | Shared report content/export modules; service PDF adapter and hosted object storage | Structured report content and filenames can be compared. PDF rendering and storage are intentionally adapter-specific; PDF bytes should not be compared because rendering metadata/layout engines can differ. |
| Preparation, persistence, and recovery | Colab paths, notebook cache state, and local files | `audit_core/audit_preparation.py` plus worker output, Supabase, and hosted object storage adapters | Semantics should remain equivalent for resume/checkpoints, but persistence mechanisms differ by design. Compare recovered audit state and final records, not storage implementation. |
| Runner/deployment | Self-contained checked-in `.ipynb`; `scripts/build_notebook.py` regenerates shared cells | Native worker starts at `hosted/service_runner.py`; Cloud Run build/deploy | The notebook is generated at development time and committed, not automatically rewritten by a web deployment. The new CI workflow guards against a stale committed notebook; it does not publish or auto-commit it. |

## Existing parity evidence

- `tests/test_audit_pipeline.py::test_fixture_result_matches_notebook_orchestration`
  runs deterministic whole-audit fixtures with Reddit both off and on, plus
  partial SERP, unavailable ChatGPT, no selected competitors, and partial Reddit
  scenarios. It compares normalized results and generated non-PDF artifacts.
- `tests/test_research_fallback.py::test_resumed_provider_race_matches_service_and_notebook_paths`
  resumes both paths from the same saved Gemini snapshot and verifies neither
  triggers replacement provider requests.
- The same file checks stage order and the social prefetch/seventh-stage
  behavior.
- Stage-level tests compare embedded notebook adapters with importable core
  behavior for company, competitor scope, profile, visibility, reporting, and
  selected parsing/transport policies.
- `tests/test_notebook_builder.py::test_checked_in_notebook_is_current` and
  `scripts/build_notebook.py --check` verify deterministic source embedding.
- A clean-runtime local smoke test loads all generated engine cells without the
  repository on `sys.path`, with a dummy Colab secret and blocked network, then
  verifies the notebook adapter hands its stage ports to the shared coordinator.
  It is Colab-style, not a session in Google's hosted Colab runtime.
- A service-native and a notebook audit were both completed live for Apple / US /
  premium smartphone with matching settings. Both selected `samsung.com` and
  `google.com` and completed 8/8 search queries. Generated buyer questions
  differed; ChatGPT succeeded in both, while Gemini failed strict US-market
  acknowledgement in the service run and succeeded in the resumed notebook run.
  This validates both live paths and the notebook resume path, but is not a
  deterministic request-for-request parity proof. See the live comparison in
  [the execution plan](SERVICE_FIRST_NOTEBOOK_PLAN.md).

## Recommended order

1. **Complete:** Add cross-path fixtures for partial and degraded results:
   partial search, unavailable answer engine, no selected competitors, Reddit
   partial coverage, and resume from a saved research snapshot.
2. **Complete:** Replace the duplicated stage sequence with the shared
   `audit_core.audit_pipeline.run_audit_pipeline`; preserve notebook stage
   labels, progress callbacks, Colab paths, and output variables in the thin
   notebook adapter. Obsolete builder templates were removed, and shared
   pipeline/parity fixtures cover the generated notebook path.
3. For any remaining pure logic found during implementation, move one bounded
   unit at a time into `audit_core`, regenerate the notebook, and require the
   CI sync and relevant parity tests to pass.
4. **Complete locally:** Load the generated notebook in an isolated Colab-style
   runtime and exercise its adapter with fixture/dry-run dependencies. A real
   Google Colab launch remains a separate check. An explicitly approved live
   provider comparison was completed and its result count reviewed; it does not
   replace deterministic offline parity fixtures.

## Scope guardrails

- Do not mirror web authentication, trial/workshop quotas, organizer tools,
  Supabase history, or Cloud Run job-control logic into the notebook.
- Do not replace a missing measured provider answer with an answer from a
  different provider or a locally generated answer.
- Do not enable a new hosted engine default or deploy as part of parity work.
- The service-native live worker has completed one standard live audit at
  1 vCPU / 1 GiB; that is operational evidence for that configuration, not
  notebook parity or Reddit-enabled/concurrent-load evidence.
