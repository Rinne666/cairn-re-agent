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

See [the architecture note](docs/architecture.md) for invariants and extension points.

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
