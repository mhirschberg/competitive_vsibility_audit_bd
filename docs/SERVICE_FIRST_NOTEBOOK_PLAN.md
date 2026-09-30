# Service-first audit engine with a generated notebook

Status: design for `feature/service-first-notebook`; no production switch.

First checkpoint: the worker can now import `app.py` without loading Gradio.
This is not yet a measured production-memory reduction; the container still
installs Gradio and the runner builder still lives in `app.py`.

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
2. Extract the runner builder from `app.py` into a lightweight module so the
   hosted worker no longer imports Gradio. Keep the current notebook-based
   runner and public behavior unchanged. Measure this small change separately.
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
