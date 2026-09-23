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

- [ ] Write tests for all nine exact required `WorkerOutput` field names; missing/extra fields; non-empty finding/relation/suggestion strings; object properties; valid `completed|failed` status; `WorkerArtifact` valid and invalid `kind`/`path`/`sha256`/`summary`/`size`/`provenance`; all seven allowed and one forbidden relation kinds; source/target key types; category-kind consistency; duplicate entity keys; float confidence type and `[0,1]` bounds; `source_entity_keys` string element types; required SuggestedIntent fields/enums; and the three-suggestion limit.
- [ ] From `C:\Users\18165\.config\superpowers\worktrees\reverse\real-pi-worker-loop\backend`, run `& 'C:\Users\18165\Desktop\reverse\backend\.venv\Scripts\python.exe' -m pytest tests\test_worker_protocol.py tests\test_runner.py -q` and confirm the new assertions fail for the intended missing behavior.
- [ ] Implement `WorkerRelation` with the seven allowed relation kinds and explicit endpoint keys; make `WorkerOutput` require all listed fields and forbid extras.
- [ ] Add a model-level check against duplicate entity keys across finding categories and cap suggested intents at three.
- [ ] Update MockDriver to return explicit relations rather than relying on Runner inference.
- [ ] Re-run the focused command above and require it to pass.

### Task 2: PiDriver process, prompt, strict parse, and telemetry

**Files:**
- Modify: `backend/app/drivers/pi.py`
- Modify: `backend/app/drivers/__init__.py`
- Modify: `backend/app/worker_protocol.py` (generic driver metrics contract only if required)
- Create: `backend/tests/test_pi_driver.py`

- [ ] Write process-level tests for valid Pi event stream, malformed JSON/Markdown without repair, exactly one schema retry, exhausted retry, process nonzero exit, valid `status="failed"`, raw stdout/stderr, token usage, and exact no-tools/no-session/no-extension argv.
- [ ] Add Windows tests proving npm `.cmd` and `.ps1` resolve to the adjacent Node entrypoint, Node/script paths with spaces remain distinct argv items, exact no-tools/no-session flags survive resolution, explicit `node <entrypoint>` works when a shim cannot be resolved, and unsupported shims fail clearly. Run `& 'C:\Users\18165\Desktop\reverse\backend\.venv\Scripts\python.exe' -m pytest tests\test_pi_driver.py -q` from the worktree `backend` directory and confirm new tests fail as expected.
- [ ] Resolve `pi.cmd`/`pi.ps1` through the generated npm shim to its Node CLI entrypoint and execute `node.exe` directly with argv; never interpolate prompt/context into a shell command.
- [ ] Invoke Pi in JSON/noninteractive mode with no tools, session, extensions, skills, prompt templates, or context files.
- [ ] Add the minimal prompt requiring JSON-only output, distinguishing all four finding categories, forbidding unsupported Facts and graph-completion speculation, limiting suggestions to three, and requiring explicit relations. Assert every requirement in tests; parse only final assistant text and perform at most one Pydantic retry without stripping Markdown or auto-repairing JSON.
- [ ] Preserve raw output and usage/retry/schema metadata outside the serialized WorkerOutput.
- [ ] Re-run the focused PiDriver tests. Then run one live smoke call via the real Pi CLI and verify a persisted/returned `WorkerOutput` before implementing the full 20-run verifier.

### Task 3: Atomic explicit graph ingestion and consistent failures

**Files:**
- Modify: `backend/app/services/runner.py`
- Modify: `backend/app/services/intents.py`
- Modify: `backend/app/services/context.py`
- Test: `backend/tests/test_runner.py`
- Test: `backend/tests/test_context.py`

- [ ] Write failing tests for Context exact goal/intent, categorized local facts/evidence/hypotheses/program nodes, complete local relation records (source/target entity keys, kind, properties), budget, and empty `available_tools`; explicit relation ingestion; zero inferred evidence→hypothesis edges; unresolved endpoints; Fact verified by returned and existing Evidence; unsupported Fact; Pi process error; exhausted retry; well-formed failed output; graph/edge/suggestion non-mutation; WorkerRun/Intent/Worker last-outcome agreement; Worker availability; duplicate-intent metrics; and a database error rolling back all semantic writes before failure persistence.
- [ ] Run `& 'C:\Users\18165\Desktop\reverse\backend\.venv\Scripts\python.exe' -m pytest tests\test_context.py tests\test_runner.py -q` from worktree `backend` and confirm the assertions fail at the missing behavior.
- [ ] Include every specified Context field and assert each payload value in `test_context.py`; resolve output relations against output findings and existing same-project nodes; reject unresolved relations before graph mutation.
- [ ] Require each returned Fact to have explicit outgoing `verified_by` to returned/existing Evidence; record unsupported count/rate and reject the entire output atomically.
- [ ] Remove Cartesian-product edges and all Runner-created semantic relations not in WorkerOutput (including the automatic intent-produced edge; worker-suggested intent sources remain in IntentSource, not an inferred Worker relation).
- [ ] On every worker failure, roll back semantic graph changes, then persist raw diagnostics/metrics, failed Intent and WorkerRun, Worker `last_run_status=failed` and operational `status=idle`; return failed RunResult. A DB persistence failure is reported distinctly and does not claim the failed state was saved.
- [ ] On success, apply findings, explicit relations, and suggested intents in one transaction; compute deduped intent counts from the existing dedupe key.
- [ ] Re-run focused tests, then run the full suite with `& 'C:\Users\18165\Desktop\reverse\backend\.venv\Scripts\python.exe' -m pytest -q` from worktree `backend`.

### Task 4: Heartbeat over the real process lifetime

**Files:**
- Modify: `backend/app/services/runner.py`
- Modify: `backend/app/services/intents.py`
- Modify: `backend/app/config.py` only if a heartbeat interval setting is required
- Test: `backend/tests/test_intents.py`
- Test: `backend/tests/test_runner.py`

- [ ] Write failing tests showing heartbeat extends both timestamps, stops after driver completion, aborts on renewal/ownership loss, terminates the Pi child on lease loss/cancellation, makes no graph writes for the canceled run, and a long-running driver cannot be reclaimed past its original lease.
- [ ] Run `& 'C:\Users\18165\Desktop\reverse\backend\.venv\Scripts\python.exe' -m pytest tests\test_intents.py tests\test_runner.py -q` from worktree `backend`; confirm the heartbeat lifecycle assertions fail first.
- [ ] Commit claim/run state before awaiting the external process.
- [ ] Run a heartbeat every `min(30s, lease/3)` using separate short-lived sessions; cancel and await it in `finally`.
- [ ] Cancel/fail the driver if renewal fails or ownership is lost; ensure Pi subprocess is terminated on cancellation.
- [ ] Re-run focused tests and verify a second session cannot reclaim a live long-running intent.

### Task 5: Repeatable real-Pi experiment and report

**Files:**
- Create: `backend/app/verify_pi_worker.py`
- Create: `backend/tests/test_verify_pi_worker.py` (pure control/summary logic only)
- Create: `docs/reports/2026-09-24-pi-worker-20-run-experiment.md`
- Modify: `README.md`

- [ ] Write tests for exact run count, one-at-a-time unique continuation intents, zero tool availability, failure reporting, and metric denominator reconciliation without invoking Pi.
- [ ] Run `& 'C:\Users\18165\Desktop\reverse\backend\.venv\Scripts\python.exe' -m pytest tests\test_verify_pi_worker.py -q` from worktree `backend` and confirm the new assertions fail first.
- [ ] Add `python -m app.verify_pi_worker --runs 20` (run from worktree `backend`) to create a fresh demo project in the ignored `backend\cairn.db`, one Pi worker, and exactly 20 sequential WorkerRuns; create only one uniquely numbered continuation Intent between calls when necessary.
- [ ] Ensure the verifier requires Pi CLI plus the configured Pi default provider/model, sets `available_tools=[]`, persists run metrics, and never invokes an external reverse tool. Document setup and the exact command in README.
- [ ] Run all deterministic tests with `& 'C:\Users\18165\Desktop\reverse\backend\.venv\Scripts\python.exe' -m pytest -q` and lint with `& 'C:\Users\18165\Desktop\reverse\backend\.venv\Scripts\python.exe' -m ruff check app tests` from worktree `backend`.
- [ ] Execute the exact command `& 'C:\Users\18165\Desktop\reverse\backend\.venv\Scripts\python.exe' -m app.verify_pi_worker --runs 20` from the isolated worktree `backend` directory. Require 20 persisted sequential runs; pass only when all 20 are completed with valid schema and consistent WorkerRun/Intent/Worker outcomes, no unresolved relations, and zero unsupported Facts. If not, preserve evidence, diagnose, fix test-first, and rerun with a fresh isolated worktree database.
- [ ] Reconcile every reported count/rate with the persisted 20 `WorkerRun` rows: success / 20; schema-invalid Pydantic responses / all Pi invocations including retries; suggestions already present by dedupe key (including repeats within one output) / total suggestions; unsupported Facts / all returned Facts (zero when denominator is zero). Include aggregate `token_input` and `token_output` totals and per-run means; total and mean duration; token/duration totals include retries. Record Pi CLI version, provider/model, budget, prompt/schema SHA-256, database path, experiment/project IDs, timestamps, and all 20 WorkerRun IDs. Require no duplicate graph/intent rows. Include failure modes, protocol weaknesses, and Ghidra readiness.

### Task 6: Final audit

**Files:**
- Review all changed backend files and the experiment report.

- [ ] Verify every required protocol field, seven relation kinds, missing/extra-field rejection, context edge list, failure path, heartbeat stop/loss behavior, state consistency, per-run metrics, and no-tool setting against code and tests.
- [ ] Require 20 real Pi WorkerRuns and inspect their persisted statuses/output summaries; require every RunResult to match its WorkerRun and Intent.
- [ ] Recompute the report rates from the persisted rows and require exact reconciliation.
- [ ] Confirm no frontend, Ghidra, GDB, Frida, search algorithm, ontology, or unrelated runtime changes.
- [ ] Present the branch and validation evidence; do not push or merge without an explicit follow-up request.
