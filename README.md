# Cairn

Graph-native autonomous reverse engineering engine. Cairn externalizes long-running
analysis into three shared graphs:

- **Exploration Graph** — why the system chose each search direction.
- **Program Graph** — functions, strings, APIs and relationships in the binary.
- **Evidence Graph** — observations, evidence, hypotheses and contradictions.

The repository is an executable MVP, not a UI-only mock. A deterministic worker can
claim an intent, assemble bounded context, produce evidence, update graphs, add a
follow-up intent and publish the entire transition over WebSocket.

## Run locally

### 1. Backend (zero-Docker quick start)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The quick start uses SQLite at `backend/cairn.db`. The API and OpenAPI UI are at
`http://localhost:8000` and `http://localhost:8000/docs`.

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, initialize the demo case, then run a worker from the
left rail. Watch the Evidence graph and intent queue update.

### PostgreSQL mode

```powershell
docker compose up -d postgres
$env:CAIRN_DATABASE_URL = "postgresql+asyncpg://cairn:cairn@localhost:5432/cairn"
cd backend
uvicorn app.main:app --reload
```

## Tests and build

```powershell
cd backend
pytest
ruff check app tests

cd ..\frontend
npm run build
```

## Worker protocol

`backend/app/worker_protocol.py` is the critical compatibility boundary. Drivers
receive goal, intent, local graph context, failed directions, tools and budget. They
return separately typed observations, evidence, hypotheses, facts, artifacts and
suggested intents.

The included drivers are:

- `mock` — deterministic and safe; exercises the full orchestration path.
- `pi` — JSON-over-stdio adapter configured by `CAIRN_PI_COMMAND`.

To verify the real Pi closed loop, configure an available Pi provider/model explicitly
and run this from `backend` (the experiment creates a fresh demo project in the configured
database and makes no reverse-tool calls):

```powershell
$env:CAIRN_PI_COMMAND = "pi --provider openai --model gpt-4.1-mini"
python -m app.verify_pi_worker --runs 20
```

The command reports persisted WorkerRun IDs, schema/retry/finding metrics, tokens,
durations, and graph/intent deduplication checks. The model/provider must be reachable
and have usable quota; auth readiness alone does not prove API availability.

See [the architecture note](docs/architecture.md) for invariants and extension points.

### Graph Orchestrator (first phase)

The optional Pi Graph Orchestrator uses the existing `CAIRN_PI_COMMAND`. When configured,
it makes one structured Pi call after project creation or a meaningful Worker result; one
schema retry is allowed. `POST /api/v1/projects/{project_id}/orchestrate` runs it manually.
Its context is bounded and excludes raw Program Graph dumps and event history.

Worker `suggested_intents` are staged as pending proposals, not immediately added to the
claimable frontier. The Orchestrator may accept, merge, or reject them; Runtime validates
source entities, deduplicates, and enforces a maximum of three new intents per tick and
the configured project budget. Invalid output is recorded as an `orchestrator.failed`
event with stdout/stderr diagnostics and does not mutate the graph or frontier.

## Implemented API surface

- Projects: create, demo seed, list, start, pause
- Graph: snapshot, node/edge upsert, 1–2 hop neighborhood
- Intents: create/deduplicate, list, heartbeat, complete
- Workers: create, run once, concurrent scheduler tick
- Binaries: authorized local ingest with SHA-256 and size limit
- Artifacts: project listing and root-confined download
- Events: durable REST history and live WebSocket stream

## Safety boundary

No real sample is analyzed by default. The current `work/` scope case remains pending
until an authorized local sample is explicitly supplied. Ghidra/Pi adapters must not
turn that pending case into a target action.
