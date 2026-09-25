from sqlalchemy import func, select

from app.models import Event, GraphNode, Intent, Project, Worker
from app.orchestrator_protocol import OrchestratorOutput, OrchestratorRun
from app.schemas import EdgeCreate, NodeCreate
from app.services.graph import upsert_edge, upsert_node
from app.services.intents import claim_next_intent
from app.services.orchestrator import orchestrate_project
from app.services.orchestrator_context import assemble_orchestrator_context
from app.services.runner import seed_demo


def proposal(description="Verify whether sub_401200 compares the supplied license buffer"):
    return {
        "description": description,
        "source_entity_keys": ["function:demo:401200"],
        "goal_relevance": "high",
        "information_gain": "high",
        "novelty": "high",
        "confidence": "medium",
        "expected_cost": "low",
        "reason": "This resolves a concrete validation question using its input path.",
    }


def output(**overrides):
    data = {
        "state_summary": "The candidate function is reachable, but its comparison is unverified.",
        "focus": "Determine whether sub_401200 compares the input against a fixed key.",
        "intents_to_create": [],
        "intents_to_close": [],
        "intents_to_deprioritize": [],
        "critical_unknowns": ["Comparison operands remain unknown."],
        "convergence_status": "continue",
        "convergence_reason": "One validation question remains open.",
    }
    return OrchestratorOutput.model_validate({**data, **overrides})


class FakeOrchestrator:
    def __init__(self, result):
        self.result = result
        self.context = None
        self.calls = 0

    async def run_orchestrator(self, context):
        self.calls += 1
        self.context = context
        return self.result


async def test_orchestrator_context_is_compressed_and_excludes_program_dump(session):
    project = await seed_demo(session)
    session.add_all(
        [
            GraphNode(
                project_id=project.id,
                graph_type="program",
                kind="Function",
                label=f"function {index} " + "x" * 200,
                entity_key=f"function:bulk:{index}",
                properties={"decompile": "secret raw dump " * 500},
            )
            for index in range(80)
        ]
    )
    session.add_all(
        [
            GraphNode(
                project_id=project.id,
                graph_type="evidence",
                kind="Hypothesis",
                label=f"hypothesis {index} " + "y" * 500,
                entity_key=f"hypothesis:bulk:{index}",
                properties={
                    "unknowns": ["unknown " + "z" * 800 for _ in range(20)],
                    "decompile": "must not be copied",
                },
            )
            for index in range(30)
        ]
    )
    await session.flush()

    context = await assemble_orchestrator_context(session, project.id)
    encoded = context.model_dump_json()

    assert len(context.active_hypotheses) <= 12
    assert len(context.open_intents) <= 20
    assert len(context.critical_unknowns) <= 20
    assert "program_nodes" not in encoded
    assert "raw dump" not in encoded
    assert "must not be copied" not in encoded
    assert len(encoded) < 30_000
    assert "limits" in context.budget and "usage" in context.budget


async def test_orchestrator_admits_at_most_three_and_dedupes_repeat(session):
    project = await seed_demo(session)
    function = await session.scalar(
        select(GraphNode).where(
            GraphNode.project_id == project.id,
            GraphNode.kind == "Function",
            GraphNode.label == "sub_401200",
        )
    )
    created = [
        {
            **proposal(f"Verify comparison detail {index} for sub_401200"),
            "source_entity_keys": [function.entity_key],
        }
        for index in range(3)
    ]
    fake = FakeOrchestrator(
        OrchestratorRun(
            output(intents_to_create=created),
            duration_seconds=0.2,
            schema_valid=True,
            token_input=100,
            token_output=50,
        )
    )

    first = await orchestrate_project(session, project.id, driver=fake)
    second = await orchestrate_project(session, project.id, driver=fake)

    assert first.created_intents == 3
    assert second.created_intents == 0
    all_intents = list(
        (await session.scalars(select(Intent).where(Intent.project_id == project.id))).all()
    )
    assert len(all_intents) == 4
    assert fake.context.budget["usage"]["intents"] >= 1


async def test_orchestrator_can_merge_pending_worker_proposals(session):
    project = await seed_demo(session)
    function = await session.scalar(
        select(GraphNode).where(
            GraphNode.project_id == project.id,
            GraphNode.kind == "Function",
            GraphNode.label == "sub_401200",
        )
    )
    suggestion = {
        "description": "Inspect whether this candidate compares the key length",
        "source_entity_keys": [function.entity_key],
        "goal_relevance": "high",
        "information_gain": "medium",
        "novelty": "medium",
        "confidence": "medium",
        "expected_cost": "low",
    }
    project.config = {
        **project.config,
        "orchestrator": {
            "pending_worker_proposals": [
                {"proposal_id": "worker-proposal-a", **suggestion},
                {"proposal_id": "worker-proposal-b", **suggestion},
            ]
        },
    }
    merged = {
        **proposal("Verify whether comparison length depends on the supplied buffer"),
        "source_entity_keys": [function.entity_key],
    }
    fake = FakeOrchestrator(
        OrchestratorRun(
            output(intents_to_create=[merged]),
            duration_seconds=0.2,
            schema_valid=True,
        )
    )

    result = await orchestrate_project(session, project.id, driver=fake)

    assert result.created_intents == 1
    assert len(fake.context.pending_worker_proposals) == 2
    refreshed = await session.get(Project, project.id)
    assert refreshed.config["orchestrator"]["pending_worker_proposals"] == []


async def test_open_frontier_cap_rejects_new_intent(session):
    project = await seed_demo(session)
    function = await session.scalar(
        select(GraphNode).where(
            GraphNode.project_id == project.id,
            GraphNode.kind == "Function",
            GraphNode.label == "sub_401200",
        )
    )
    project.config = {**project.config, "budget": {"max_open_intents": 1}}
    fake = FakeOrchestrator(
        OrchestratorRun(
            output(
                intents_to_create=[
                    {
                        **proposal(),
                        "source_entity_keys": [function.entity_key],
                    }
                ]
            ),
            duration_seconds=0.1,
            schema_valid=True,
        )
    )

    result = await orchestrate_project(session, project.id, driver=fake)

    assert result.created_intents == 0
    assert result.status == "continue"
    assert fake.calls == 1
    assert (
        await session.scalar(
            select(Intent.id).where(
                Intent.project_id == project.id,
                Intent.creator == "orchestrator:pi",
            )
        )
        is None
    )


async def test_graph_growth_budget_caps_intent_graph_nodes(session):
    project = await seed_demo(session)
    function = await session.scalar(
        select(GraphNode).where(
            GraphNode.project_id == project.id,
            GraphNode.kind == "Function",
            GraphNode.label == "sub_401200",
        )
    )
    project.config = {**project.config, "budget": {"max_graph_nodes": 8}}
    proposals = [
        {
            **proposal(f"Verify graph-budget comparison property {index}"),
            "source_entity_keys": [function.entity_key],
        }
        for index in range(3)
    ]
    fake = FakeOrchestrator(
        OrchestratorRun(
            output(intents_to_create=proposals),
            duration_seconds=0.1,
            schema_valid=True,
        )
    )

    result = await orchestrate_project(session, project.id, driver=fake)

    assert result.created_intents == 2
    assert result.status == "paused"
    node_count = await session.scalar(
        select(func.count(GraphNode.id)).where(GraphNode.project_id == project.id)
    )
    assert node_count == 8


async def test_unknown_source_entity_rejects_decision_without_graph_mutation(session):
    project = await seed_demo(session)
    fake = FakeOrchestrator(
        OrchestratorRun(
            output(
                intents_to_create=[
                    {
                        **proposal(),
                        "source_entity_keys": ["function:missing"],
                    }
                ]
            ),
            duration_seconds=0.1,
            schema_valid=True,
        )
    )

    result = await orchestrate_project(session, project.id, driver=fake)

    assert result.status == "failed"
    assert "unknown source" in result.error
    assert (
        await session.scalar(
            select(Intent.id).where(
                Intent.project_id == project.id,
                Intent.creator == "orchestrator:pi",
            )
        )
        is None
    )
    assert await session.scalar(
        select(Event.id).where(Event.project_id == project.id, Event.kind == "orchestrator.failed")
    )


async def test_orchestrator_failure_preserves_graph_and_frontier(session):
    project = await seed_demo(session)
    before_nodes = await session.scalar(
        select(GraphNode.id).where(GraphNode.project_id == project.id).limit(1)
    )
    before_intent = await session.scalar(
        select(Intent).where(Intent.project_id == project.id, Intent.status == "open")
    )
    fake = FakeOrchestrator(
        OrchestratorRun(
            None,
            duration_seconds=1.0,
            schema_invalid_attempts=2,
            retry_count=1,
            stdout="not json",
            stderr="provider diagnostic",
            error="invalid schema",
        )
    )

    result = await orchestrate_project(session, project.id, driver=fake)

    assert result.status == "failed"
    assert (await session.get(Intent, before_intent.id)).status == "open"
    event = await session.scalar(
        select(Event).where(Event.project_id == project.id, Event.kind == "orchestrator.failed")
    )
    assert event.payload["diagnostics"] == {
        "stdout": "not json",
        "stderr": "provider diagnostic",
    }
    assert await session.get(GraphNode, before_nodes) is not None


async def test_closed_intent_is_not_claimable_and_empty_frontier_can_stall(session):
    project = await seed_demo(session)
    intent = await session.scalar(select(Intent).where(Intent.project_id == project.id))
    worker = await session.scalar(select(Worker).where(Worker.project_id == project.id))
    fake = FakeOrchestrator(
        OrchestratorRun(
            output(
                intents_to_close=[intent.id],
                convergence_status="stalled",
                critical_unknowns=["Still need a concrete validation result."],
            ),
            duration_seconds=0.1,
            schema_valid=True,
        )
    )

    result = await orchestrate_project(session, project.id, driver=fake)

    assert result.status == "stalled"
    assert (await session.get(Intent, intent.id)).status == "closed"
    assert await claim_next_intent(session, project.id, worker.id) is None
    assert (await session.get(Project, project.id)).status == "stalled"


async def test_completed_convergence_requires_verified_evidence(session):
    project = await seed_demo(session)
    complete_output = output(
        convergence_status="completed",
        critical_unknowns=[],
        convergence_reason="A verified conclusion answers the goal.",
    )
    no_evidence = await orchestrate_project(
        session,
        project.id,
        driver=FakeOrchestrator(OrchestratorRun(complete_output, 0.1, schema_valid=True)),
    )
    assert no_evidence.status == "continue"
    assert (await session.get(Project, project.id)).status == "running"

    fact = await session.scalar(
        select(GraphNode).where(GraphNode.project_id == project.id, GraphNode.kind == "Fact")
    )
    evidence = await upsert_node(
        session,
        project.id,
        NodeCreate(
            graph_type="evidence",
            kind="Evidence",
            label="Observed license comparison",
            entity_key="evidence:verified-comparison",
            properties={},
            confidence=0.95,
        ),
    )
    await upsert_edge(
        session,
        project.id,
        EdgeCreate(
            source_node_id=fact.id,
            target_node_id=evidence.id,
            kind="verified_by",
        ),
    )
    completed = await orchestrate_project(
        session,
        project.id,
        driver=FakeOrchestrator(OrchestratorRun(complete_output, 0.1, schema_valid=True)),
    )
    assert completed.status == "completed"
    assert (await session.get(Project, project.id)).status == "completed"


async def test_runtime_budget_blocks_new_intent_even_if_model_proposes_it(session):
    project = await seed_demo(session)
    function = await session.scalar(
        select(GraphNode).where(
            GraphNode.project_id == project.id,
            GraphNode.kind == "Function",
            GraphNode.label == "sub_401200",
        )
    )
    project.config = {**project.config, "budget": {"max_worker_runs": 0}}
    fake = FakeOrchestrator(
        OrchestratorRun(
            output(intents_to_create=[{**proposal(), "source_entity_keys": [function.entity_key]}]),
            duration_seconds=0.1,
            schema_valid=True,
        )
    )

    result = await orchestrate_project(session, project.id, driver=fake)

    assert result.created_intents == 0
    assert result.status == "paused"
    assert fake.calls == 0
    assert (await session.get(Project, project.id)).status == "paused"
