# Real Pi Worker Closed Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate 20 sequential real Pi Worker runs across the existing graph/context/driver boundary with strict structured outputs and safe graph updates.

**Architecture:** Keep the existing Python Pydantic protocol and `AgentDriver` interface. `PiDriver` owns Pi CLI process details and returns only validated `WorkerOutput`; Runner owns graph ingestion, intent outcomes, and generic metrics. Lease refresh uses the existing heartbeat service with short-lived independent DB sessions; no schema migration or frontend work.

**Tech Stack:** Python 3.12, Pydantic 2, FastAPI, SQLAlchemy async, pytest/pytest-asyncio, locally installed Pi CLI.

---

### Task 1: Strict Worker protocol and relation semantics

**Files:**
- Modify: `backend/app/worker_protocol.py`
- Modify: `backend/app/drivers/mock.py`
- Test: `backend/tests/test_worker_protocol.py`
- Test: `backend/tests/test_runner.py`

- [x] Write tests for all nine exact required `WorkerOutput` field names; missing/extra fields; non-empty finding/relation/suggestion strings; object properties; valid `completed|failed` status; `WorkerArtifact` valid and invalid `kind`/`path`/`sha256`/`summary`/`size`/`provenance`; all seven allowed and one forbidden relation kinds; source/target key types; category-kind consistency; duplicate entity keys; float confidence type and `[0,1]` bounds; `source_entity_keys` string element types; required SuggestedIntent fields/enums; and the three-suggestion limit.
- [x] From the worktree `backend` directory, run the focused protocol/runner suite and confirm the new assertions fail for the intended missing behavior.
- [x] Implement `WorkerRelation` with the seven allowed relation kinds and explicit endpoint keys; make `WorkerOutput` require all listed fields and forbid extras.
- [x] Add a model-level check against duplicate entity keys across finding categories and cap suggested intents at three.
- [x] Update MockDriver to return explicit relations rather than relying on Runner inference.
- [x] Re-run the focused command above and require it to pass.

### Task 2: PiDriver process, prompt, strict parse, and telemetry

**Files:**
- Modify: `backend/app/drivers/pi.py`
- Modify: `backend/app/drivers/__init__.py`
- Modify: `backend/app/worker_protocol.py` (generic driver metrics contract only if required)
- Create: `backend/tests/test_pi_driver.py`

- [x] Write process-level tests for valid Pi event stream, malformed JSON/Markdown without repair, exactly one schema retry, exhausted retry, process nonzero exit, valid `status="failed"`, raw stdout/stderr, token usage, and exact no-tools/no-session/no-extension argv.
- [x] Add Windows tests proving npm `.cmd` and `.ps1` resolve to the adjacent Node entrypoint, Node/script paths with spaces remain distinct argv items, exact no-tools/no-session flags survive resolution, explicit `node <entrypoint>` works, and unsupported shims fail clearly. Confirmed the new tests fail before implementing command resolution.
- [x] Resolve `pi.cmd`/`pi.ps1` through the generated npm shim to its Node CLI entrypoint and execute `node.exe` directly with argv; never interpolate prompt/context into a shell command.
- [x] Invoke Pi in JSON/noninteractive mode with no tools, session, extensions, skills, prompt templates, or context files.
- [x] Add the minimal prompt requiring JSON-only output, distinguishing all four finding categories, forbidding unsupported Facts and graph-completion speculation, limiting suggestions to three, and requiring explicit relations. Assert every requirement in tests; parse only final assistant text and perform at most one Pydantic retry without stripping Markdown or auto-repairing JSON.
- [x] Preserve raw output and usage/retry/schema metadata outside the serialized WorkerOutput.
- [x] Re-run the focused PiDriver tests. A real CLI smoke was run and its failure was persisted, but no valid WorkerOutput was obtained because every configured provider failed; repeat the live-success gate when a provider is available.

### Task 3: Atomic explicit graph ingestion and consistent failures

**Files:**
- Modify: `backend/app/services/runner.py`
- Modify: `backend/app/services/intents.py`
- Modify: `backend/app/services/context.py`
- Test: `backend/tests/test_runner.py`
- Test: `backend/tests/test_context.py`

- [x] Write tests for Context exact goal/intent, categorized local facts/evidence/hypotheses/program nodes, complete local relation records (source/target entity keys, kind, properties), budget, and empty `available_tools`; explicit relation ingestion; zero inferred evidence→hypothesis edges; unresolved endpoints; Fact verified by existing Evidence; unsupported Fact; Pi process error; well-formed failed output; graph/edge/suggestion non-mutation; WorkerRun/Intent/Worker last-outcome agreement; and duplicate-intent metrics. A DB commit-error injection test remains optional audit work.
- [x] Run the focused context/runner suite and confirm it exposes the missing context/relation/status behavior.
- [x] Include every specified Context field and assert each payload value in `test_context.py`; resolve output relations against output findings and existing same-project nodes; reject unresolved relations before graph mutation.
- [x] Require each returned Fact to have explicit outgoing `verified_by` to returned/existing Evidence; record unsupported count/rate and reject the entire output atomically.
- [x] Remove Cartesian-product edges and all Runner-created semantic relations not in WorkerOutput (including the automatic intent-produced edge; worker-suggested intent sources remain in IntentSource, not an inferred Worker relation).
- [x] On worker failure, roll back semantic graph changes, then persist raw diagnostics/metrics, failed Intent and WorkerRun, Worker `last_run_status=failed` and operational `status=idle`; return failed RunResult. DB persistence failure injection remains untested.
- [x] On success, apply findings, explicit relations, and suggested intents in one transaction; compute deduped intent counts from the existing dedupe key.
- [x] Re-run focused tests; rerun the full suite once more after final edits.

### Task 4: Heartbeat over the real process lifetime

**Files:**
- Modify: `backend/app/services/runner.py`
- Modify: `backend/app/services/intents.py`
- Modify: `backend/app/config.py` only if a heartbeat interval setting is required
- Test: `backend/tests/test_intents.py`
- Test: `backend/tests/test_runner.py`

- [x] Write tests showing heartbeat extends both timestamps, stops after driver completion, aborts on renewal/ownership loss, cancels a driver on lease loss, makes no graph writes for the canceled run, and a long-running driver cannot be reclaimed past its original lease. Pi child cancellation is also unit-tested.
- [ ] Run `& 'C:\Users\18165\Desktop\reverse\backend\.venv\Scripts\python.exe' -m pytest tests\test_intents.py tests\test_runner.py -q` from worktree `backend`; confirm the heartbeat lifecycle assertions fail first.
- [x] Commit claim/run state before awaiting the external process.
- [x] Run a heartbeat every `min(30s, lease/3)` using separate short-lived sessions; cancel and await it in `finally`.
- [x] Cancel/fail the driver if renewal fails or ownership is lost; ensure Pi subprocess is terminated on cancellation.
- [x] Re-run focused tests and verify a second session cannot reclaim a live long-running intent.

### Task 5: Repeatable real-Pi experiment and report

**Files:**
- Create: `backend/app/verify_pi_worker.py`
- Create: `backend/tests/test_verify_pi_worker.py` (pure control/summary logic only)
- Create: `docs/reports/2026-09-24-pi-worker-20-run-experiment.md`
- Modify: `README.md`

- [x] Write tests for exact run count, one-at-a-time unique continuation intents, zero tool availability, failure reporting, and metric denominator reconciliation without invoking Pi.
- [x] Run verifier control tests (`4 passed`); these were written after the implementation, so no pre-implementation red run was recorded.
- [x] Add `python -m app.verify_pi_worker --runs 20` (run from worktree `backend`) to create a fresh demo project in the ignored `backend\cairn.db`, one Pi worker, and sequential WorkerRuns; create a unique continuation Intent only when no Pi suggestion is claimable.
- [x] Ensure the verifier requires Pi CLI plus explicit provider/model, sets `available_tools=[]`, persists run metrics, and never invokes an external reverse tool. Document setup and the command in README.
- [x] Run all deterministic tests and lint from worktree `backend`: `84 passed`; Ruff clean.
- [ ] Execute the exact command `& 'C:\Users\18165\Desktop\reverse\backend\.venv\Scripts\python.exe' -m app.verify_pi_worker --runs 20` from the isolated worktree `backend` directory. Diagnostic real Pi runs failed at provider availability (MiniMax quota exhausted; OpenAI timeout; Anthropic 403), so the 20-run acceptance experiment has not been executed. Resume when an available provider/network is restored.
- [ ] Reconcile every reported count/rate with the persisted 20 `WorkerRun` rows: success / 20; schema-invalid Pydantic responses / all Pi invocations including retries; suggestions already present by dedupe key (including repeats within one output) / total suggestions; unsupported Facts / all returned Facts (zero when denominator is zero). Include aggregate `token_input` and `token_output` totals and per-run means; total and mean duration; token/duration totals include retries. Record Pi CLI version, provider/model, budget, prompt/schema SHA-256, database path, experiment/project IDs, timestamps, and all 20 WorkerRun IDs. Require no duplicate graph/intent rows. Include failure modes, protocol weaknesses, and Ghidra readiness.

### Task 6: Final audit

**Files:**
- Review all changed backend files and the experiment report.

- [x] Verify every required protocol field, seven relation kinds, missing/extra-field rejection, context edge list, failure path, heartbeat stop/loss behavior, state consistency, per-run metrics, and no-tool setting against code and tests.
- [ ] Require 20 real Pi WorkerRuns and inspect their persisted statuses/output summaries; require every RunResult to match its WorkerRun and Intent.
- [ ] Recompute the report rates from the persisted rows and require exact reconciliation.
- [x] Confirm no frontend, Ghidra, GDB, Frida, search algorithm, ontology, or unrelated runtime changes.
- [ ] Present the branch and validation evidence; do not push or merge without an explicit follow-up request.
