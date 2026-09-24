# Real Pi Worker closed-loop experiment

**Status: incomplete — the required 20 successful runs have not been demonstrated.**

## What changed

- Made `WorkerOutput` strict and explicit, including relation endpoints and the seven allowed relation kinds.
- Added Pi CLI isolation, JSONL final-message extraction, one schema-only retry, Windows npm-shim resolution, raw diagnostics, and first-provider-error termination.
- Made context include local graph relations with `available_tools=[]`.
- Changed graph ingestion to prevalidate endpoints and Fact verification, ingest only explicit relations, deduplicate suggested intents, and persist failures without semantic graph writes.
- Added lease heartbeat, generic per-run telemetry, and `python -m app.verify_pi_worker --runs 20`.

## Real Pi attempts and observed failures

Pi CLI version: `0.84.4`. Four real Pi WorkerRuns were persisted across smoke/preflight attempts; none received a model response that could be validated as `WorkerOutput`.

| Provider / model | WorkerRun ID | Result |
| --- | --- | --- |
| `minimax-cn` / configured default `MiniMax-M3` | `f6db2626-a6bd-4f1f-9c3c-cc35f6f73056` | HTTP 429: local token-plan quota exhausted. This exposed Pi's internal retries and the adapter's then-missing API-error detection; both are now handled by stopping on the first error event. |
| `openai` / `gpt-4.1-mini` | `3c2893e5-18ac-4784-a47a-65ae134f0141` | Pi returned `Request timed out.` |
| `openai` / `gpt-4.1-mini` | `640a3869-13dc-4689-a555-bdd322496c7d` | Fail-fast verifier smoke; `Request timed out.` after one Pi process invocation. |
| `anthropic` / `claude-haiku-4-5` | `9760c323-a9be-4505-b39d-4a0d847524e3` | HTTP 403: `Request not allowed`. |

Across those four diagnostic runs: **0/4 schema-valid completions**, **0 input / 0 output tokens**, and **105.36 seconds** total recorded driver duration. The first run (before API-error classification was fixed) recorded one schema retry and two invalid empty responses; the later three runs correctly recorded zero schema retries and zero schema-invalid attempts because they failed at the provider boundary. These diagnostic probes span adapter revisions and are not a substitute for the final 20-run rate calculation.

Each failed run persisted `WorkerRun=failed`, `Intent=failed`, `Worker.status=idle`, and `Worker.metadata.last_run_status=failed`. Each demo project retained only its six seeded nodes and five seeded edges; no Worker finding or relation was ingested.

The 20-run verifier smoke records these identifiers and hashes:

- OpenAI preflight experiment: `6c7c5165-7540-4bdd-abc7-58c8cd20f4bd`; project `4411e625-cf9e-45b7-b9bc-9e79430f0bdc`.
- Anthropic preflight experiment: `d8e5b3ea-8610-431e-9eb8-bf80b115d756`; project `65ba2c83-761d-4844-83ad-504b6cbb6920`.
- Prompt SHA-256: `7960231caae958fea57d7aa3f0914de07729d1211f14bdacc18846bdaa36c4b7`.
- WorkerOutput schema SHA-256: `79eb813a53957790449127ba244b7aebeb9967ce7ed56e73c7993b4690a968ca`.
- Database: isolated worktree `backend/cairn.db`.

## Verification and remaining work

- Deterministic backend tests: **84 passed**; Ruff: **all checks passed**; `git diff --check` is clean.
- The verifier's control path was exercised with deterministic tests for sequential run count, empty tools, continuation intents, and fail-fast reporting; those tests do not count as real Pi runs.
- Protocol weakness still worth observing during a successful run: non-Fact relations are restricted to the seven core names and real endpoints, but only Fact → Evidence has a semantic type rule. No broader ontology was added.
- **Ghidra integration is not ready to claim**: the architecture boundary is in place, but the essential real-Pi structured-output loop has not passed. Resume the exact 20-run command after a configured provider has usable quota and network access.
