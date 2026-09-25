from __future__ import annotations

from collections import Counter
from datetime import UTC
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GraphEdge, GraphNode, Intent, IntentSource, Project, WorkerRun, utcnow
from app.orchestrator_protocol import OrchestratorContext

_FINAL_INTENT_LIMIT = 10
_UNKNOWN_LIMIT = 20


def _short(value: Any, limit: int = 500) -> str:
    return str(value or "")[:limit]


def _finding(node: GraphNode) -> dict[str, Any]:
    properties = node.properties if isinstance(node.properties, dict) else {}
    return {
        "entity_key": node.entity_key,
        "kind": node.kind,
        "label": _short(node.label, 255),
        "confidence": round(float(node.confidence), 3),
        "assumptions": [_short(item, 200) for item in properties.get("assumptions", [])[:3]]
        if isinstance(properties.get("assumptions"), list)
        else [],
        "unknowns": [_short(item, 200) for item in properties.get("unknowns", [])[:3]]
        if isinstance(properties.get("unknowns"), list)
        else [],
        "validation_plan": [_short(item, 200) for item in properties.get("validation_plan", [])[:3]]
        if isinstance(properties.get("validation_plan"), list)
        else [],
    }


async def assemble_orchestrator_context(
    session: AsyncSession, project_id: str
) -> OrchestratorContext:
    """Build a bounded strategic view; never serialize the whole graph or event log."""
    project = await session.get(Project, project_id)
    if project is None:
        raise ValueError("project not found")

    confirmed_nodes = list(
        (
            await session.scalars(
                select(GraphNode)
                .where(
                    GraphNode.project_id == project_id,
                    GraphNode.kind.in_(["Fact", "Conclusion"]),
                )
                .order_by(GraphNode.created_at.desc())
                .limit(12)
            )
        ).all()
    )
    hypothesis_nodes = list(
        (
            await session.scalars(
                select(GraphNode)
                .where(
                    GraphNode.project_id == project_id,
                    GraphNode.kind == "Hypothesis",
                    GraphNode.status.notin_(["rejected", "resolved", "closed"]),
                )
                .order_by(GraphNode.confidence.desc(), GraphNode.created_at.desc())
                .limit(12)
            )
        ).all()
    )
    findings = [*confirmed_nodes, *hypothesis_nodes]
    finding_ids = [node.id for node in findings]
    edges = (
        list(
            (
                await session.scalars(
                    select(GraphEdge)
                    .where(
                        GraphEdge.project_id == project_id,
                        GraphEdge.kind.in_(["supports", "contradicts", "verified_by"]),
                        or_(
                            GraphEdge.source_node_id.in_(finding_ids),
                            GraphEdge.target_node_id.in_(finding_ids),
                        ),
                    )
                    .order_by(GraphEdge.created_at.desc())
                    .limit(200)
                )
            ).all()
        )
        if finding_ids
        else []
    )
    edge_endpoint_ids = {
        node_id for edge in edges for node_id in (edge.source_node_id, edge.target_node_id)
    } - set(finding_ids)
    target_nodes = (
        list(
            (
                await session.scalars(
                    select(GraphNode).where(
                        GraphNode.project_id == project_id,
                        GraphNode.id.in_(edge_endpoint_ids),
                    )
                )
            ).all()
        )
        if edge_endpoint_ids
        else []
    )
    by_id = {node.id: node for node in [*findings, *target_nodes]}
    support_counts: Counter[str] = Counter()
    contradiction_counts: Counter[str] = Counter()
    for edge in edges:
        source = by_id.get(edge.source_node_id)
        if source is None:
            continue
        if edge.kind in {"supports", "verified_by"}:
            if source.kind in {"Fact", "Conclusion", "Hypothesis"}:
                support_counts[source.entity_key] += 1
            target = by_id.get(edge.target_node_id)
            if target and target.kind in {"Fact", "Conclusion", "Hypothesis"}:
                support_counts[target.entity_key] += 1
        elif edge.kind == "contradicts":
            contradiction_counts[source.entity_key] += 1
            target = by_id.get(edge.target_node_id)
            if target:
                contradiction_counts[target.entity_key] += 1

    confirmed = [
        {
            **_finding(node),
            "supporting_evidence_count": support_counts[node.entity_key],
        }
        for node in confirmed_nodes
    ]
    hypotheses = [
        {
            **_finding(node),
            "supporting_evidence_count": support_counts[node.entity_key],
            "contradiction_count": contradiction_counts[node.entity_key],
            "status": node.status,
        }
        for node in hypothesis_nodes
    ]
    contradictions = [
        {
            "source": by_id[edge.source_node_id].entity_key,
            "target": by_id[edge.target_node_id].entity_key,
            "kind": edge.kind,
        }
        for edge in edges
        if edge.kind == "contradicts"
        and edge.source_node_id in by_id
        and edge.target_node_id in by_id
    ][:12]

    critical_unknowns: list[dict[str, Any]] = []
    for hypothesis in hypotheses:
        for unknown in hypothesis["unknowns"]:
            if len(critical_unknowns) >= _UNKNOWN_LIMIT:
                break
            critical_unknowns.append({"hypothesis": hypothesis["entity_key"], "question": unknown})

    recent_evidence_nodes = list(
        (
            await session.scalars(
                select(GraphNode)
                .where(GraphNode.project_id == project_id, GraphNode.kind == "Evidence")
                .order_by(GraphNode.created_at.desc())
                .limit(16)
            )
        ).all()
    )
    recent_evidence = [_finding(node) for node in recent_evidence_nodes]

    open_intents = list(
        (
            await session.scalars(
                select(Intent)
                .where(Intent.project_id == project_id, Intent.status == "open")
                .order_by(Intent.priority.desc(), Intent.created_at)
                .limit(20)
            )
        ).all()
    )
    sources_by_intent: dict[str, list[str]] = {intent.id: [] for intent in open_intents}
    if open_intents:
        source_rows = (
            await session.execute(
                select(IntentSource.intent_id, GraphNode.entity_key)
                .join(GraphNode, GraphNode.id == IntentSource.node_id)
                .where(IntentSource.intent_id.in_(list(sources_by_intent)))
            )
        ).all()
        for intent_id, entity_key in source_rows:
            sources_by_intent[intent_id].append(entity_key)

    def pack_intent(intent: Intent) -> dict[str, Any]:
        return {
            "id": intent.id,
            "description": _short(intent.description, 1000),
            "priority": round(float(intent.priority), 4),
            "source_entity_keys": sources_by_intent.get(intent.id, []),
        }

    final_intents = list(
        (
            await session.scalars(
                select(Intent)
                .where(
                    Intent.project_id == project_id,
                    Intent.status.in_(["completed", "failed"]),
                )
                .order_by(Intent.completed_at.desc(), Intent.created_at.desc())
                .limit(_FINAL_INTENT_LIMIT)
            )
        ).all()
    )
    finished_ids = [intent.id for intent in final_intents]
    if finished_ids:
        for intent_id in finished_ids:
            sources_by_intent.setdefault(intent_id, [])
        finished_sources = (
            await session.execute(
                select(IntentSource.intent_id, GraphNode.entity_key)
                .join(GraphNode, GraphNode.id == IntentSource.node_id)
                .where(IntentSource.intent_id.in_(finished_ids))
            )
        ).all()
        for intent_id, entity_key in finished_sources:
            sources_by_intent[intent_id].append(entity_key)
    completed = [pack_intent(item) for item in final_intents if item.status == "completed"][:10]
    failed = [pack_intent(item) for item in final_intents if item.status == "failed"][:10]

    config = project.config if isinstance(project.config, dict) else {}
    orchestrator_state = config.get("orchestrator", {})
    if not isinstance(orchestrator_state, dict):
        orchestrator_state = {}
    raw_pending = orchestrator_state.get("pending_worker_proposals", [])
    raw_pending = raw_pending[-20:] if isinstance(raw_pending, list) else []
    pending = [
        {
            "proposal_id": _short(item.get("proposal_id"), 64),
            "description": _short(item.get("description"), 1000),
            "source_entity_keys": [
                _short(key, 320) for key in item.get("source_entity_keys", [])[:8]
            ],
            "goal_relevance": item.get("goal_relevance", "medium"),
            "information_gain": item.get("information_gain", "medium"),
            "novelty": item.get("novelty", "medium"),
            "confidence": item.get("confidence", "medium"),
            "expected_cost": item.get("expected_cost", "medium"),
            "proposed_by": _short(item.get("proposed_by"), 120),
        }
        for item in raw_pending
        if isinstance(item, dict)
    ]

    budget_limits = config.get("budget", {})
    if not isinstance(budget_limits, dict):
        budget_limits = {}
    allowed_budget_keys = {
        "max_tokens",
        "max_worker_runs",
        "max_wall_time_seconds",
        "max_graph_nodes",
        "max_intents",
        "max_open_intents",
        "max_tool_calls",
    }
    worker_run_count = await session.scalar(
        select(func.count(WorkerRun.id))
        .join(Intent, Intent.id == WorkerRun.intent_id)
        .where(Intent.project_id == project_id)
    )
    worker_tokens = await session.scalar(
        select(func.coalesce(func.sum(WorkerRun.token_input + WorkerRun.token_output), 0))
        .join(Intent, Intent.id == WorkerRun.intent_id)
        .where(Intent.project_id == project_id)
    )
    raw_orchestrator_tokens = orchestrator_state.get("token_usage", 0)
    orchestrator_tokens = (
        raw_orchestrator_tokens
        if type(raw_orchestrator_tokens) is int and raw_orchestrator_tokens >= 0
        else 0
    )
    open_intent_count = await session.scalar(
        select(func.count(Intent.id)).where(
            Intent.project_id == project_id, Intent.status == "open"
        )
    )
    created_at = project.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    budget = {
        "limits": {
            key: value
            for key, value in budget_limits.items()
            if key in allowed_budget_keys and type(value) is int and value >= 0
        },
        "usage": {
            "worker_runs": worker_run_count or 0,
            "tokens": (worker_tokens or 0) + orchestrator_tokens,
            "elapsed_seconds": max(0, int((utcnow() - created_at).total_seconds())),
            "graph_nodes": await session.scalar(
                select(func.count(GraphNode.id)).where(GraphNode.project_id == project_id)
            ),
            "intents": await session.scalar(
                select(func.count(Intent.id)).where(Intent.project_id == project_id)
            ),
            "open_intents": open_intent_count or 0,
        },
    }

    return OrchestratorContext(
        goal=_short(project.goal, 4000),
        confirmed_findings=confirmed,
        active_hypotheses=hypotheses,
        contradictions=contradictions,
        critical_unknowns=critical_unknowns,
        active_branches=[
            {
                "intent_id": intent.id,
                "source_entity_keys": sources_by_intent.get(intent.id, []),
            }
            for intent in open_intents
        ],
        failed_branches=failed,
        recent_evidence=recent_evidence,
        recently_completed_intents=completed,
        recently_failed_intents=failed,
        open_intents=[pack_intent(item) for item in open_intents],
        pending_worker_proposals=pending,
        budget=budget,
    )
