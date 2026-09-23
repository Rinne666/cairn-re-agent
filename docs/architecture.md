# Cairn MVP architecture

Cairn treats reverse engineering as a persistent search problem. Agent sessions are
replaceable compute; PostgreSQL and the artifact directory are the durable state.

```text
API / WebSocket
      |
Graph Engine ---- Context Assembler
      |                    |
Intent Queue -------- Worker Runner ---- AgentDriver
      |                    |                 |-- MockDriver
Event Log             Result Ingest          `-- PiDriver (JSON stdio)
      |                    |
      `------------- PostgreSQL + artifacts
```

## Stable boundaries

1. **Graph Engine** owns typed nodes/edges, deduplication, local graph retrieval and
   provenance. It does not import an agent runtime.
2. **Worker Protocol** is the Pydantic `WorkerContext` / `WorkerOutput` contract.
   Observations, evidence, hypotheses and facts remain distinct collections.
3. **Harness** claims one leased intent, assembles a bounded context, invokes an
   `AgentDriver`, ingests results and proposes follow-up intents.
4. **Reverse Tools** implement `ReverseToolProvider`; Ghidra, GDB and Frida remain
   replaceable providers rather than dependencies of the graph engine.

## Invariants

- `(project_id, entity_key)` identifies a graph entity.
- `(project_id, normalized description, source nodes)` identifies an intent.
- Hypotheses never become facts merely because a worker emitted them.
- Every worker output receives a `worker_run_id` provenance link.
- Large outputs belong in artifacts; graph properties contain summaries only.
- A claim is recoverable after its lease expires.
- PostgreSQL claims use `FOR UPDATE SKIP LOCKED` through SQLAlchemy.

## Graph presentation contract

The stored graph is canonical analysis state; the main canvas is a bounded cognitive
projection. Summary mode shows functions with the strongest relationships, confirmed
facts, active intents, and hypotheses. Evidence and observations stay stored as graph
entities but appear on demand through support/conflict counts. Low-ranked functions
collapse into an expandable cluster. Analysis mode expands selected relationships in a
bounded local neighborhood; raw properties and event history stay in the Inspector and
Timeline.

For address-bearing program entities, the graph service canonicalizes keys by entity
kind, binary (or project when no binary is attached), and normalized address. Other
semantic entities keep the driver's `entity_key`, which remains responsible for
providing a stable identity across worker runs.

## Current MVP seam

The demo deliberately uses `MockDriver`. Configure `CAIRN_PI_COMMAND` and create a
worker with `driver="pi"` to use a JSON-over-stdio Pi wrapper. The wrapper must read
one `WorkerContext` JSON document from stdin and emit one `WorkerOutput` JSON document
on stdout. This keeps Pi-specific prompting and process management outside the graph
engine.

Real Ghidra execution is intentionally not faked. A concrete provider should implement
`ReverseToolProvider` only after an authorized local sample and a working Ghidra bridge
are available.
