from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers import get_driver
from app.models import GraphNode, Project, Worker, WorkerRun, utcnow
from app.schemas import EdgeCreate, IntentCreate, NodeCreate, PrioritySignals, RunResult
from app.services.context import assemble_context
from app.services.events import emit_event
from app.services.graph import upsert_edge, upsert_node
from app.services.intents import claim_next_intent, create_intent


async def run_once(session: AsyncSession, project_id: str, worker_id: str) -> RunResult | None:
    intent = await claim_next_intent(session, project_id, worker_id)
    if intent is None:
        return None
    worker = await session.get(Worker, worker_id)
    if worker is None:
        raise ValueError("worker not found")
    context = await assemble_context(session, intent)
    intent.status = "running"
    run = WorkerRun(
        worker_id=worker_id,
        intent_id=intent.id,
        input_context=context.model_dump(),
    )
    session.add(run)
    await session.flush()
    await emit_event(
        session, project_id, "worker.started", {"worker_id": worker_id, "intent_id": intent.id}
    )

    driver = get_driver(worker.driver)
    try:
        output = await driver.run_agent(context)
        entity_nodes: dict[str, GraphNode] = {}
        created_nodes = 0
        for graph_type, findings in (
            ("evidence", output.observations),
            ("evidence", output.evidence),
            ("evidence", output.hypotheses),
            ("exploration", output.facts),
        ):
            for finding in findings:
                node = await upsert_node(
                    session,
                    project_id,
                    NodeCreate(
                        graph_type=graph_type,
                        kind=finding.kind,
                        label=finding.label,
                        entity_key=finding.entity_key,
                        properties={
                            **finding.properties,
                            "provenance": {
                                **finding.properties.get("provenance", {}),
                                "worker_run_id": run.id,
                            },
                        },
                        confidence=finding.confidence,
                        created_by=f"worker:{worker_id}",
                    ),
                )
                entity_nodes[finding.entity_key] = node
                created_nodes += 1

        observation_nodes = [
            entity_nodes[item.entity_key]
            for item in output.observations
            if item.entity_key in entity_nodes
        ]
        for evidence in output.evidence:
            evidence_node = entity_nodes.get(evidence.entity_key)
            if evidence_node:
                for observation in observation_nodes:
                    await upsert_edge(
                        session,
                        project_id,
                        EdgeCreate(
                            source_node_id=evidence_node.id,
                            target_node_id=observation.id,
                            kind="derived_from",
                            created_by=f"worker:{worker_id}",
                        ),
                    )
        evidence_nodes = [
            entity_nodes[item.entity_key]
            for item in output.evidence
            if item.entity_key in entity_nodes
        ]
        for hypothesis in output.hypotheses:
            hypothesis_node = entity_nodes.get(hypothesis.entity_key)
            if hypothesis_node:
                for evidence_node in evidence_nodes:
                    await upsert_edge(
                        session,
                        project_id,
                        EdgeCreate(
                            source_node_id=evidence_node.id,
                            target_node_id=hypothesis_node.id,
                            kind="supports",
                            created_by=f"worker:{worker_id}",
                        ),
                    )

        created_intents = 0
        for suggested in output.suggested_intents:
            source_ids = [
                entity_nodes[key].id for key in suggested.source_entity_keys if key in entity_nodes
            ]
            await create_intent(
                session,
                project_id,
                IntentCreate(
                    description=suggested.description,
                    source_node_ids=source_ids,
                    creator=f"worker:{worker_id}",
                    signals=PrioritySignals(
                        goal_relevance=suggested.goal_relevance,
                        information_gain=suggested.information_gain,
                        confidence=suggested.confidence,
                        expected_cost=suggested.expected_cost,
                    ),
                ),
            )
            created_intents += 1

        intent.status = "completed"
        intent.completed_at = utcnow()
        if output.hypotheses:
            intent.result_node_id = entity_nodes[output.hypotheses[0].entity_key].id
        intent_node = await session.get(GraphNode, intent.metadata_json.get("exploration_node_id"))
        if intent_node:
            intent_node.status = "completed"
            intent_node.properties = {
                **intent_node.properties,
                "status": "completed",
                "result_node_id": intent.result_node_id,
            }
            if intent.result_node_id:
                await upsert_edge(
                    session,
                    project_id,
                    EdgeCreate(
                        source_node_id=intent_node.id,
                        target_node_id=intent.result_node_id,
                        kind="produced",
                        created_by=f"worker:{worker_id}",
                    ),
                )
        worker.status = "idle"
        worker.last_seen_at = utcnow()
        run.status = output.status
        run.output_summary = output.model_dump()
        run.finished_at = utcnow()
        await emit_event(
            session,
            project_id,
            "intent.completed",
            {
                "intent_id": intent.id,
                "worker_id": worker_id,
                "result_node_id": intent.result_node_id,
            },
        )
        await emit_event(
            session,
            project_id,
            "worker.finished",
            {"worker_id": worker_id, "worker_run_id": run.id},
        )
        return RunResult(
            worker_id=worker_id,
            intent_id=intent.id,
            worker_run_id=run.id,
            status=output.status,
            created_nodes=created_nodes,
            created_intents=created_intents,
        )
    except Exception as exc:
        intent.status = "failed"
        worker.status = "idle"
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = utcnow()
        await emit_event(
            session,
            project_id,
            "intent.failed",
            {"intent_id": intent.id, "worker_id": worker_id, "error": str(exc)},
        )
        raise


async def seed_demo(session: AsyncSession) -> Project:
    project = Project(
        name="CrackMe // License Path",
        goal=(
            "Find how the program validates the license key and support "
            "the conclusion with evidence."
        ),
        status="running",
        config={"budget": {"max_tool_calls": 12, "max_tokens": 16000}},
    )
    session.add(project)
    await session.flush()
    await emit_event(session, project.id, "project.created", {"project_id": project.id})

    function_nodes = []
    for address, label, detail in (
        ("401050", "main", "Reads argv and dispatches validation"),
        ("401200", "sub_401200", "Candidate license transformation"),
        ("403100", "memcmp", "Imported comparison routine"),
    ):
        function_nodes.append(
            await upsert_node(
                session,
                project.id,
                NodeCreate(
                    graph_type="program",
                    kind="Function",
                    label=label,
                    entity_key=f"function:demo:{address}",
                    properties={"address": f"0x{address}", "summary": detail},
                    created_by="demo-seed",
                ),
            )
        )
    string_node = await upsert_node(
        session,
        project.id,
        NodeCreate(
            graph_type="program",
            kind="String",
            label="invalid key",
            entity_key="string:demo:invalid-key",
            properties={"address": "0x408100"},
            created_by="demo-seed",
        ),
    )
    await upsert_edge(
        session,
        project.id,
        EdgeCreate(
            source_node_id=function_nodes[0].id, target_node_id=function_nodes[1].id, kind="calls"
        ),
    )
    await upsert_edge(
        session,
        project.id,
        EdgeCreate(
            source_node_id=function_nodes[1].id, target_node_id=function_nodes[2].id, kind="calls"
        ),
    )
    await upsert_edge(
        session,
        project.id,
        EdgeCreate(
            source_node_id=function_nodes[1].id, target_node_id=string_node.id, kind="references"
        ),
    )
    fact = await upsert_node(
        session,
        project.id,
        NodeCreate(
            graph_type="exploration",
            kind="Fact",
            label="Input reaches sub_401200",
            entity_key="fact:demo:input-reaches-401200",
            properties={"basis": "call graph and argv data flow"},
            confidence=0.92,
            created_by="demo-seed",
        ),
    )
    await create_intent(
        session,
        project.id,
        IntentCreate(
            description="Trace function 0x401200 and inspect its input/output relationship.",
            source_node_ids=[fact.id, function_nodes[1].id],
            creator="demo-seed",
            signals=PrioritySignals(
                goal_relevance="high",
                information_gain="high",
                confidence="high",
                expected_cost="medium",
            ),
        ),
    )
    for index in range(1, 4):
        session.add(
            Worker(
                project_id=project.id,
                name=f"worker-{index:02d}",
                driver="mock",
                model="deterministic-demo",
            )
        )
    await session.flush()
    return project
