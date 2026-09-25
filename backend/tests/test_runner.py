import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import GraphEdge, GraphNode, Intent, Project, Worker, WorkerRun
from app.schemas import NodeCreate
from app.services.graph import upsert_node
from app.services.runner import run_once, seed_demo
from app.worker_protocol import AgentRun, WorkerFinding, WorkerOutput, WorkerRelation


async def test_worker_run_extends_evidence_graph_and_queue(session):
    project = await seed_demo(session)
    await session.flush()
    worker = await session.scalar(select(Worker).where(Worker.project_id == project.id))
    assert worker is not None

    result = await run_once(session, project.id, worker.id)

    assert result is not None
    assert result.status == "completed"
    assert result.created_nodes == 3
    assert result.created_intents == 0

    hypothesis = await session.scalar(
        select(GraphNode).where(GraphNode.project_id == project.id, GraphNode.kind == "Hypothesis")
    )
    assert hypothesis is not None
    assert hypothesis.confidence < 1.0
    support_count = await session.scalar(
        select(func.count(GraphEdge.id)).where(GraphEdge.kind == "supports")
    )
    assert support_count == 1
    open_intents = await session.scalar(
        select(func.count(Intent.id)).where(
            Intent.project_id == project.id, Intent.status == "open"
        )
    )
    assert open_intents == 0
    project = await session.get(Project, project.id)
    assert len(project.config["orchestrator"]["pending_worker_proposals"]) == 1


def output_with(*, relations=None, status="completed", include_fact=False):
    evidence = WorkerFinding(
        kind="Evidence",
        label="call edge from supplied graph",
        entity_key="ev:test",
        properties={},
        confidence=0.9,
    )
    hypothesis = WorkerFinding(
        kind="Hypothesis",
        label="candidate validation",
        entity_key="hyp:test",
        properties={},
        confidence=0.6,
    )
    fact_items = (
        [
            WorkerFinding(
                kind="Fact",
                label="function validates key",
                entity_key="fact:test",
                properties={},
                confidence=0.95,
            )
        ]
        if include_fact
        else []
    )
    return WorkerOutput(
        observations=[
            WorkerFinding(
                kind="Observation",
                label="input reaches function",
                entity_key="obs:test",
                properties={},
                confidence=0.8,
            )
        ],
        evidence=[evidence],
        hypotheses=[hypothesis],
        facts=fact_items,
        relations=relations or [],
        artifacts=[],
        suggested_intents=[],
        status=status,
        summary="bounded analysis result",
    )


async def _run_with_output(session, monkeypatch, project, worker, output):
    async def run_agent(context):
        return AgentRun(output, duration_seconds=0.01, schema_valid=True)

    monkeypatch.setattr(
        "app.services.runner.get_driver", lambda _: SimpleNamespace(run_agent=run_agent)
    )
    return await run_once(session, project.id, worker.id)


async def test_runner_ingests_only_explicit_relations_and_no_cartesian_edges(session, monkeypatch):
    project = await seed_demo(session)
    worker = await session.scalar(select(Worker).where(Worker.project_id == project.id))
    explicit = WorkerRelation(
        source_entity_key="ev:test", target_entity_key="hyp:test", kind="supports", properties={}
    )
    result = await _run_with_output(
        session, monkeypatch, project, worker, output_with(relations=[explicit])
    )

    assert result.status == "completed"
    created_edges = list(
        (
            await session.scalars(
                select(GraphEdge).where(
                    GraphEdge.project_id == project.id,
                    GraphEdge.created_by == f"worker:{worker.id}",
                )
            )
        ).all()
    )
    assert [(edge.kind, edge.source_node_id, edge.target_node_id) for edge in created_edges] == [
        ("supports", created_edges[0].source_node_id, created_edges[0].target_node_id)
    ]
    source = await session.get(GraphNode, created_edges[0].source_node_id)
    target = await session.get(GraphNode, created_edges[0].target_node_id)
    assert (source.entity_key, target.entity_key) == ("ev:test", "hyp:test")


async def test_worker_failed_output_does_not_complete_intent_or_ingest_graph(session, monkeypatch):
    project = await seed_demo(session)
    worker = await session.scalar(select(Worker).where(Worker.project_id == project.id))
    before = await session.scalar(
        select(GraphNode).where(
            GraphNode.project_id == project.id, GraphNode.entity_key == "obs:test"
        )
    )
    result = await _run_with_output(
        session, monkeypatch, project, worker, output_with(status="failed")
    )
    intent = await session.get(Intent, result.intent_id)
    run = await session.get(WorkerRun, result.worker_run_id)
    assert result.status == "failed"
    assert intent.status == "failed"
    assert run.status == "failed"
    assert before is None
    assert (
        await session.scalar(
            select(GraphNode).where(
                GraphNode.project_id == project.id, GraphNode.entity_key == "obs:test"
            )
        )
        is None
    )


async def test_fact_without_explicit_verified_by_evidence_fails_atomically(session, monkeypatch):
    project = await seed_demo(session)
    project_id = project.id
    worker = await session.scalar(select(Worker).where(Worker.project_id == project.id))
    result = await _run_with_output(
        session, monkeypatch, project, worker, output_with(include_fact=True)
    )
    assert result.status == "failed"
    assert (
        await session.scalar(
            select(GraphNode).where(
                GraphNode.project_id == project_id, GraphNode.entity_key == "ev:test"
            )
        )
        is None
    )
    assert (
        await session.scalar(
            select(GraphNode).where(
                GraphNode.project_id == project_id, GraphNode.entity_key == "fact:test"
            )
        )
        is None
    )
    run = await session.get(WorkerRun, result.worker_run_id)
    assert run.output_summary["unsupported_fact_count"] == 1
    assert run.output_summary["unsupported_fact_rate"] == 1.0


async def test_fact_can_be_verified_by_existing_evidence(session, monkeypatch):
    project = await seed_demo(session)
    worker = await session.scalar(select(Worker).where(Worker.project_id == project.id))
    existing_evidence = await upsert_node(
        session,
        project.id,
        NodeCreate(
            graph_type="evidence",
            kind="Evidence",
            label="Known validation call",
            entity_key="evidence:existing",
            properties={"source": "demo"},
            confidence=0.9,
            created_by="demo-seed",
        ),
    )
    verified_relation = WorkerRelation(
        source_entity_key="fact:test",
        target_entity_key=existing_evidence.entity_key,
        kind="verified_by",
        properties={"basis": "existing graph evidence"},
    )
    result = await _run_with_output(
        session,
        monkeypatch,
        project,
        worker,
        output_with(include_fact=True, relations=[verified_relation]),
    )
    assert result.status == "completed"
    fact = await session.scalar(
        select(GraphNode).where(
            GraphNode.project_id == project.id, GraphNode.entity_key == "fact:test"
        )
    )
    assert fact is not None
    edge = await session.scalar(
        select(GraphEdge).where(
            GraphEdge.project_id == project.id,
            GraphEdge.source_node_id == fact.id,
            GraphEdge.target_node_id == existing_evidence.id,
            GraphEdge.kind == "verified_by",
        )
    )
    assert fact is not None and edge is not None


async def test_unresolved_relation_endpoint_fails_without_graph_mutation(session, monkeypatch):
    project = await seed_demo(session)
    project_id = project.id
    worker = await session.scalar(select(Worker).where(Worker.project_id == project.id))
    bad_relation = WorkerRelation(
        source_entity_key="ev:test",
        target_entity_key="missing:node",
        kind="supports",
        properties={},
    )
    result = await _run_with_output(
        session, monkeypatch, project, worker, output_with(relations=[bad_relation])
    )
    assert result.status == "failed"
    run = await session.get(WorkerRun, result.worker_run_id)
    assert run.output_summary["unresolved_relation_count"] == 1
    assert (
        await session.scalar(
            select(GraphNode).where(
                GraphNode.project_id == project_id, GraphNode.entity_key == "ev:test"
            )
        )
        is None
    )


async def test_finding_cannot_overwrite_existing_node_with_another_kind(session, monkeypatch):
    project = await seed_demo(session)
    project_id = project.id
    worker = await session.scalar(select(Worker).where(Worker.project_id == project_id))
    conflicting_output = WorkerOutput.model_validate(
        {
            **output_with().model_dump(),
            "evidence": [
                {
                    "kind": "Evidence",
                    "label": "Reclassified function",
                    "entity_key": f"function:{project_id}:0x401200",
                    "properties": {},
                    "confidence": 0.9,
                }
            ],
        }
    )
    result = await _run_with_output(session, monkeypatch, project, worker, conflicting_output)
    original = await session.scalar(
        select(GraphNode).where(
            GraphNode.project_id == project_id,
            GraphNode.entity_key == f"function:{project_id}:0x401200",
        )
    )
    assert result.status == "failed"
    assert original.kind == "Function"


async def test_failed_driver_output_persists_raw_diagnostics_and_metrics(session, monkeypatch):
    project = await seed_demo(session)
    project_id = project.id
    worker = await session.scalar(select(Worker).where(Worker.project_id == project.id))

    async def run_agent(context):
        return AgentRun(
            output=None,
            duration_seconds=1.25,
            token_input=17,
            token_output=9,
            retry_count=1,
            schema_valid=False,
            schema_invalid_attempts=2,
            stdout="not json",
            stderr="last provider error",
            error="invalid schema twice",
        )

    monkeypatch.setattr(
        "app.services.runner.get_driver", lambda _: SimpleNamespace(run_agent=run_agent)
    )
    result = await run_once(session, project_id, worker.id)
    intent = await session.get(Intent, result.intent_id)
    run = await session.get(WorkerRun, result.worker_run_id)
    worker = await session.get(Worker, worker.id)
    assert result.status == intent.status == run.status == "failed"
    assert worker.status == "idle"
    assert worker.metadata_json["last_run_status"] == "failed"
    assert run.token_input == 17 and run.token_output == 9
    assert run.output_summary["retry_count"] == 1
    assert run.output_summary["schema_invalid_attempts"] == 2
    assert run.output_summary["diagnostics"] == {
        "stdout": "not json",
        "stderr": "last provider error",
    }
    assert (
        await session.scalar(
            select(GraphNode).where(
                GraphNode.project_id == project_id, GraphNode.entity_key == "obs:test"
            )
        )
        is None
    )


async def test_duplicate_suggested_intent_is_deduped_and_counted(session, monkeypatch):
    project = await seed_demo(session)
    worker = await session.scalar(select(Worker).where(Worker.project_id == project.id))
    output = output_with()
    suggestion = {
        "description": "Inspect the existing candidate caller",
        "source_entity_keys": ["ev:test"],
        "goal_relevance": "high",
        "information_gain": "medium",
        "confidence": "medium",
        "expected_cost": "low",
    }
    output = WorkerOutput.model_validate(
        {**output.model_dump(), "suggested_intents": [suggestion, suggestion]}
    )
    result = await _run_with_output(session, monkeypatch, project, worker, output)
    run = await session.get(WorkerRun, result.worker_run_id)
    intents = list(
        (
            await session.scalars(
                select(Intent).where(
                    Intent.project_id == project.id,
                    Intent.description == suggestion["description"],
                )
            )
        ).all()
    )
    assert result.created_intents == 0
    assert not intents
    project = await session.get(Project, project.id)
    assert len(project.config["orchestrator"]["pending_worker_proposals"]) == 1
    assert run.output_summary["duplicate_worker_proposal_count"] == 1
    assert run.output_summary["duplicate_worker_proposal_rate"] == 0.5
    worker_edges = list(
        (
            await session.scalars(
                select(GraphEdge).where(
                    GraphEdge.project_id == project.id,
                    GraphEdge.created_by == f"worker:{worker.id}",
                )
            )
        ).all()
    )
    assert all(edge.kind != "motivates" for edge in worker_edges)


async def test_heartbeat_extends_lease_and_prevents_second_claim(session, monkeypatch):
    project = await seed_demo(session)
    project_id = project.id
    workers = list(
        (
            await session.scalars(
                select(Worker).where(Worker.project_id == project_id).order_by(Worker.created_at)
            )
        ).all()
    )
    worker, second_worker = workers[:2]
    monkeypatch.setattr(
        "app.services.runner.get_settings",
        lambda: type("Settings", (), {"intent_lease_seconds": 0.3})(),
    )
    monkeypatch.setattr(
        "app.services.intents.get_settings",
        lambda: type("Settings", (), {"intent_lease_seconds": 0.3})(),
    )
    initial = {}

    async def slow_driver(context):
        factory = async_sessionmaker(session.bind, expire_on_commit=False)
        async with factory() as observer:
            first_claim = await observer.scalar(
                select(Intent).where(Intent.project_id == project_id, Intent.status == "running")
            )
            assert first_claim is not None
            initial["lease"] = first_claim.lease_until.replace(tzinfo=UTC)
            initial["heartbeat"] = first_claim.heartbeat_at.replace(tzinfo=UTC)
        await asyncio.sleep(0.26)
        async with factory() as observer:
            running_intent = await observer.scalar(
                select(Intent).where(Intent.project_id == project_id, Intent.status == "running")
            )
            assert running_intent is not None
            lease_until = running_intent.lease_until.replace(tzinfo=UTC)
            assert lease_until > datetime.now(UTC)
            assert lease_until > initial["lease"] + timedelta(seconds=0.15)
            heartbeat_at = running_intent.heartbeat_at.replace(tzinfo=UTC)
            assert heartbeat_at > initial["heartbeat"]
            from app.services.intents import claim_next_intent

            assert await claim_next_intent(observer, project_id, second_worker.id) is None
        return AgentRun(output_with(), duration_seconds=0.26, schema_valid=True)

    monkeypatch.setattr(
        "app.services.runner.get_driver", lambda _: SimpleNamespace(run_agent=slow_driver)
    )
    result = await run_once(session, project_id, worker.id)
    run = await session.get(WorkerRun, result.worker_run_id)
    assert result.status == "completed", run.error


async def test_lost_heartbeat_cancels_driver_and_fails_without_graph_write(session, monkeypatch):
    project = await seed_demo(session)
    project_id = project.id
    worker = await session.scalar(select(Worker).where(Worker.project_id == project_id))
    cancelled = asyncio.Event()

    async def lose_lease(*args):
        raise RuntimeError("lease ownership lost")

    async def unbounded_driver(context):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr("app.services.runner._renew_lease_loop", lose_lease)
    monkeypatch.setattr(
        "app.services.runner.get_driver", lambda _: SimpleNamespace(run_agent=unbounded_driver)
    )
    result = await run_once(session, project_id, worker.id)
    run = await session.get(WorkerRun, result.worker_run_id)
    intent = await session.get(Intent, result.intent_id)
    assert cancelled.is_set()
    assert result.status == run.status == intent.status == "failed"
    assert (
        await session.scalar(
            select(GraphNode).where(
                GraphNode.project_id == project_id, GraphNode.entity_key == "obs:test"
            )
        )
        is None
    )
