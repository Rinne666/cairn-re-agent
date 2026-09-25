import asyncio
import hashlib
from contextlib import suppress
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.drivers import get_driver
from app.models import GraphNode, Intent, Project, Worker, WorkerRun, utcnow
from app.schemas import EdgeCreate, IntentCreate, NodeCreate, PrioritySignals, RunResult
from app.services.context import assemble_context
from app.services.events import emit_event
from app.services.graph import upsert_edge, upsert_node
from app.services.intents import claim_next_intent, create_intent, normalize_intent
from app.worker_protocol import AgentRun, WorkerOutput


class WorkerOutputError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        unsupported_facts: int = 0,
        unresolved_relations: int = 0,
    ) -> None:
        super().__init__(message)
        self.unsupported_facts = unsupported_facts
        self.unresolved_relations = unresolved_relations


async def _renew_lease_loop(
    session: AsyncSession,
    intent_id: str,
    worker_id: str,
    stop: asyncio.Event,
) -> None:
    session_factory = async_sessionmaker(session.bind, expire_on_commit=False)
    interval = min(30.0, max(0.1, get_settings().intent_lease_seconds / 3))
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except TimeoutError:
            pass
        async with session_factory() as heartbeat_session:
            intent = await heartbeat_session.get(Intent, intent_id)
            worker = await heartbeat_session.get(Worker, worker_id)
            if (
                intent is None
                or worker is None
                or intent.worker_id != worker_id
                or intent.status != "running"
            ):
                raise RuntimeError("worker lease lost")
            now = utcnow()
            intent.heartbeat_at = now
            intent.lease_until = now + timedelta(seconds=get_settings().intent_lease_seconds)
            worker.last_seen_at = now
            await heartbeat_session.commit()


async def _run_driver_with_heartbeat(
    session: AsyncSession, intent_id: str, worker_id: str, driver, context
) -> AgentRun:
    stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(_renew_lease_loop(session, intent_id, worker_id, stop))
    driver_task = asyncio.create_task(driver.run_agent(context))
    done, _ = await asyncio.wait({driver_task, heartbeat_task}, return_when=asyncio.FIRST_COMPLETED)
    if heartbeat_task in done and heartbeat_task.exception() is not None:
        driver_task.cancel()
        with suppress(asyncio.CancelledError):
            await driver_task
        raise RuntimeError(f"worker heartbeat failed: {heartbeat_task.exception()}")
    try:
        return await driver_task
    finally:
        stop.set()
        await heartbeat_task


def _run_metrics(
    agent_run: AgentRun,
    output: WorkerOutput | None,
    unsupported_facts: int = 0,
    unresolved_relations: int = 0,
) -> dict:
    counts = {
        "observations": len(output.observations) if output else 0,
        "evidence": len(output.evidence) if output else 0,
        "hypotheses": len(output.hypotheses) if output else 0,
        "facts": len(output.facts) if output else 0,
        "relations": len(output.relations) if output else 0,
        "suggested_intents": len(output.suggested_intents) if output else 0,
        "artifacts": len(output.artifacts) if output else 0,
    }
    return {
        "schema_valid": agent_run.schema_valid,
        "retry_count": agent_run.retry_count,
        "schema_invalid_attempts": agent_run.schema_invalid_attempts,
        "duration_seconds": round(agent_run.duration_seconds, 6),
        "token_input": agent_run.token_input,
        "token_output": agent_run.token_output,
        **{f"output_{name}_count": count for name, count in counts.items()},
        "duplicate_intent_count": 0,
        "unsupported_fact_count": unsupported_facts,
        "unresolved_relation_count": unresolved_relations,
        "unsupported_fact_rate": (unsupported_facts / counts["facts"] if counts["facts"] else 0.0),
        "diagnostics": {"stdout": agent_run.stdout, "stderr": agent_run.stderr},
    }


async def _finish_failed_run(
    session: AsyncSession,
    project_id: str,
    worker_id: str,
    intent_id: str,
    run_id: str,
    agent_run: AgentRun,
    error: str,
    output: WorkerOutput | None = None,
    unsupported_facts: int = 0,
    unresolved_relations: int = 0,
) -> RunResult:
    await session.rollback()
    intent = await session.get(Intent, intent_id)
    worker = await session.get(Worker, worker_id)
    run = await session.get(WorkerRun, run_id)
    if intent is None or worker is None or run is None:
        raise RuntimeError("cannot persist failed worker outcome: run state disappeared")
    now = utcnow()
    intent.status = "failed"
    intent.completed_at = now
    intent.lease_until = None
    intent_node = await session.get(GraphNode, intent.metadata_json.get("exploration_node_id"))
    if intent_node:
        intent_node.status = "failed"
        intent_node.properties = {**intent_node.properties, "status": "failed"}
    worker.status = "idle"
    worker.last_seen_at = now
    worker.metadata_json = {**worker.metadata_json, "last_run_status": "failed"}
    run.status = "failed"
    run.error = error
    run.finished_at = now
    run.token_input = agent_run.token_input
    run.token_output = agent_run.token_output
    run.output_summary = {
        **_run_metrics(agent_run, output, unsupported_facts, unresolved_relations),
        "worker_output": output.model_dump() if output else None,
        "error": error,
    }
    await emit_event(
        session,
        project_id,
        "intent.failed",
        {"intent_id": intent_id, "worker_id": worker_id, "error": error},
    )
    await emit_event(
        session, project_id, "worker.finished", {"worker_id": worker_id, "worker_run_id": run_id}
    )
    await session.commit()
    return RunResult(
        worker_id=worker_id,
        intent_id=intent_id,
        worker_run_id=run_id,
        status="failed",
        created_nodes=0,
        created_intents=0,
    )


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
    await session.commit()
    agent_run = AgentRun(None, 0.0)
    output: WorkerOutput | None = None
    unsupported_facts = 0
    unresolved_relations = 0
    try:
        agent_run = await _run_driver_with_heartbeat(session, intent.id, worker_id, driver, context)
        output = agent_run.output
        if output is None:
            return await _finish_failed_run(
                session,
                project_id,
                worker_id,
                intent.id,
                run.id,
                agent_run,
                agent_run.error or "Worker returned no structured output",
            )
        if output.status == "failed":
            return await _finish_failed_run(
                session,
                project_id,
                worker_id,
                intent.id,
                run.id,
                agent_run,
                output.summary or "Worker reported failed status",
                output=output,
            )
        if output.artifacts:
            raise WorkerOutputError(
                "artifacts are not accepted while no artifact tools are enabled"
            )

        existing_nodes = list(
            (
                await session.scalars(select(GraphNode).where(GraphNode.project_id == project_id))
            ).all()
        )
        entity_nodes = {node.entity_key: node for node in existing_nodes}
        all_findings = [
            ("evidence", item)
            for items in (output.observations, output.evidence, output.hypotheses)
            for item in items
        ] + [("exploration", item) for item in output.facts]
        for _, finding in all_findings:
            existing = entity_nodes.get(finding.entity_key)
            if existing and existing.kind != finding.kind:
                raise WorkerOutputError(
                    f"finding entity_key {finding.entity_key!r} conflicts with existing "
                    f"node kind {existing.kind!r}"
                )
        returned_keys = {finding.entity_key for _, finding in all_findings}
        available_keys = set(entity_nodes) | returned_keys
        for relation in output.relations:
            if (
                relation.source_entity_key not in available_keys
                or relation.target_entity_key not in available_keys
            ):
                unresolved_relations += 1
                raise WorkerOutputError(
                    "unresolved relation endpoint: "
                    f"{relation.source_entity_key} -> {relation.target_entity_key}",
                    unresolved_relations=unresolved_relations,
                )
        returned_evidence = {item.entity_key for item in output.evidence}
        existing_evidence = {node.entity_key for node in existing_nodes if node.kind == "Evidence"}
        for fact in output.facts:
            verified = any(
                relation.source_entity_key == fact.entity_key
                and relation.kind == "verified_by"
                and relation.target_entity_key in returned_evidence | existing_evidence
                for relation in output.relations
            )
            if not verified:
                unsupported_facts += 1
        if unsupported_facts:
            raise WorkerOutputError(
                f"{unsupported_facts} Fact finding(s) lack explicit verified_by Evidence relation",
                unsupported_facts=unsupported_facts,
            )
        for suggested in output.suggested_intents:
            unresolved = set(suggested.source_entity_keys) - available_keys
            if unresolved:
                raise WorkerOutputError(
                    f"unresolved suggested intent source(s): {', '.join(sorted(unresolved))}"
                )

        created_nodes = 0
        for graph_type, finding in all_findings:
            was_new = finding.entity_key not in entity_nodes
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
            created_nodes += int(was_new)

        for relation in output.relations:
            await upsert_edge(
                session,
                project_id,
                EdgeCreate(
                    source_node_id=entity_nodes[relation.source_entity_key].id,
                    target_node_id=entity_nodes[relation.target_entity_key].id,
                    kind=relation.kind,
                    properties=relation.properties,
                    created_by=f"worker:{worker_id}",
                ),
            )

        duplicate_intents = 0
        project = await session.get(Project, project_id)
        if project is None:
            raise WorkerOutputError("project disappeared while applying worker output")
        current_orchestrator_state = (project.config or {}).get("orchestrator", {})
        if not isinstance(current_orchestrator_state, dict):
            current_orchestrator_state = {}
        raw_pending_proposals = current_orchestrator_state.get("pending_worker_proposals", [])
        pending_proposals = (
            list(raw_pending_proposals) if isinstance(raw_pending_proposals, list) else []
        )
        pending_ids = {
            proposal.get("proposal_id")
            for proposal in pending_proposals
            if isinstance(proposal, dict)
        }
        for suggested in output.suggested_intents:
            source_keys = list(dict.fromkeys(suggested.source_entity_keys))
            identity = normalize_intent(suggested.description) + "|" + "|".join(sorted(source_keys))
            proposal_id = hashlib.sha256(identity.encode()).hexdigest()
            if proposal_id in pending_ids:
                duplicate_intents += 1
            else:
                pending_proposals.append(
                    {
                        "proposal_id": proposal_id,
                        "description": suggested.description,
                        "source_entity_keys": source_keys,
                        "goal_relevance": suggested.goal_relevance,
                        "information_gain": suggested.information_gain,
                        "novelty": "medium",
                        "confidence": suggested.confidence,
                        "expected_cost": suggested.expected_cost,
                        "proposed_by": worker_id,
                        "worker_run_id": run.id,
                    }
                )
                pending_ids.add(proposal_id)
        project.config = {
            **(project.config or {}),
            "orchestrator": {
                **current_orchestrator_state,
                "pending_worker_proposals": pending_proposals[-20:],
            },
        }

        agent_run_metrics = _run_metrics(agent_run, output)
        agent_run_metrics["duplicate_worker_proposal_count"] = duplicate_intents
        agent_run_metrics["duplicate_worker_proposal_rate"] = (
            duplicate_intents / len(output.suggested_intents) if output.suggested_intents else 0.0
        )

        intent.status = "completed"
        intent.completed_at = utcnow()
        intent.lease_until = None
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
        worker.status = "idle"
        worker.last_seen_at = utcnow()
        worker.metadata_json = {**worker.metadata_json, "last_run_status": "completed"}
        run.status = "completed"
        run.output_summary = {**agent_run_metrics, "worker_output": output.model_dump()}
        run.token_input = agent_run.token_input
        run.token_output = agent_run.token_output
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
        await session.commit()
        return RunResult(
            worker_id=worker_id,
            intent_id=intent.id,
            worker_run_id=run.id,
            status="completed",
            created_nodes=created_nodes,
            created_intents=0,
        )
    except Exception as exc:
        unsupported_facts = getattr(exc, "unsupported_facts", unsupported_facts)
        unresolved_relations = getattr(exc, "unresolved_relations", unresolved_relations)
        return await _finish_failed_run(
            session,
            project_id,
            worker_id,
            intent.id,
            run.id,
            agent_run,
            str(exc),
            output=output,
            unsupported_facts=unsupported_facts,
            unresolved_relations=unresolved_relations,
        )


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
