# Real Pi Worker closed-loop experiment

**Status: passed.** The final SDU experiment completed 20/20 real Pi Worker runs with consistent WorkerRun/Intent/Worker state and no unsupported Fact or duplicate-intent ingestion.

## What changed

- Kept the Graph Engine → Worker Protocol → AgentDriver → PiDriver boundary; Graph services do not import Pi.
- WorkerOutput findings and all seven relation kinds remain explicit. Graph ingestion creates only returned relations; no evidence/observation Cartesian products.
- Tightened Pi output guidance: insufficient evidence is a completed analysis, Facts require `verified_by` Evidence, and the final assistant text must contain JSON.
- Added context-aware Pydantic validation for Fact verification so one schema retry can correct unsupported Facts before Graph ingestion.
- Raised the Pi JSONL stream line limit to 1 MiB after a real large-event failure. Added strict telemetry and the sequential `--runs 20` verifier.

## Final real run

- Experiment: `80a3e682-5176-4bdd-a57c-918fff2ab8b1`; project: `bdd5b876-3331-4ab0-9855-5cb06d48733a`.
- Pi `0.84.4`, provider `sdu`, model `ByteDance-volcengine/DeepSeek-V4-Flash-GA`.
- 20/20 WorkerRuns completed; 21 Pi process invocations (one schema retry); state consistent; `available_tools=[]` throughout.
- 1/21 invalid-schema attempt (**4.76%**) was an empty-text first response and was corrected by the single retry; 0 unsupported Facts / 13 Facts; 0 duplicate suggested Intents / 51 suggestions; 0 unresolved relations.
- 79 observations, 48 evidence, 20 hypotheses, 13 facts, 194 explicit relation records, 51 suggested intents. The graph contained 107 canonical nodes and 64 edges; duplicate graph nodes/edges were 0, and all returned relation endpoints and edges were verified in the database.
- Input/output tokens: 132,522 / 198,067. Total duration: 1,782.38 s; mean 89.12 s per WorkerRun.
- Prompt SHA-256: `bd6d992e1b33936f0972ccf29c0f309ef78ddf6a427b9a1d147acae916b63b93`; WorkerOutput schema SHA-256: `79eb813a53957790449127ba244b7aebeb9967ce7ed56e73c7993b4690a968ca`.

## Observed failure modes

- MiniMax exhausted its provider quota; Kimi completed five runs, then returned HTTP 403 for its five-hour quota. These were provider limits, not Graph mutations.
- An earlier SDU batch was interrupted when its parent process disappeared, leaving an expired running lease and a stale running WorkerRun in the isolated experiment DB. Hard process termination currently has no stale-run reconciler.
- The first SDU baseline exposed an asyncio default line-buffer limit on large Pi JSONL events; fixed by increasing the stream limit.
- The next baseline completed 18/20: one output marked insufficient context as `failed`, one emitted Facts without explicit `verified_by`, and one retry returned reasoning-only content. Prompt semantics, contextual validation/retry, and final-text requirements were tightened; the final 20-run batch had none of these failures.

## Protocol weaknesses and Ghidra readiness

- The final experiment validates the Worker loop and generic driver boundary, not Ghidra artifacts or reverse-engineering accuracy; no real reverse tools were enabled.
- The seven relation types and endpoint checks are enforced, with a semantic rule for Fact → Evidence. Other relation kinds intentionally have no richer ontology.
- Ready to begin a separate Ghidra adapter integration at the existing boundary. Before production use, add recovery for process death/expired leases so stale running records are reconciled; this does not invalidate the clean 20-run result.

## Verification

- Backend tests: **87 passed**; Ruff: **all checks passed**; `git diff --check`: clean.
- Final verifier report: `passed=true`, `state_consistent=true`, 20 persisted and 20 schema-valid completed outputs.
- Implementation commits: `7f9099d`, `e0e60da`, `6e36f69`, `9c8e62a`.
