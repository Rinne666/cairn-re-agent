from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import get_settings
from app.drivers import get_orchestrator_driver
from app.models import GraphEdge, GraphNode, Intent, Project, WorkerRun, utcnow
from app.orchestrator_protocol import OrchestratorContext, OrchestratorOutput, OrchestratorRun
from app.schemas import IntentCreate, PrioritySignals
from app.services.events import emit_event
from app.services.intents import create_intent, intent_key, normalize_intent
from app.services.orchestrator_context import assemble_orchestrator_context

MAX_NEW_INTENTS_PER_TICK = 3
DEFAULT_MAX_OPEN_INTENTS = 20
DEFAULT_MAX_PROJECT_INTENTS = 100
VAGUE_INTENTS = {
    "analyze further",
    "investigate more",
    "look deeper",
    "explore related functions",
}
VAGUE_INTENT_PATTERN = re.compile(
    r"^(?:analyze|investigate)\b.*\b(?:further|more|deeper)$|"
    r"^look deeper$|^explore related functions$"
)


@dataclass
class OrchestrationResult:
    status: str
    created_intents: int = 0
    closed_intents: int = 0
    deprioritized_intents: int = 0
    token_input: int = 0
    token_output: int = 0
    retry_count: int = 0
    error: str | None = None


class OrchestratorOutputError(ValueError):
    pass


def _budget_exhausted(
    context: OrchestratorContext,
    project: Project,
    *,
    additional_tokens: int = 0,
    additional_seconds: float = 0.0,
    additional_graph_nodes: int = 0,
) -> bool:
    budget = context.budget
    usage = budget.get("usage", {})
    limits = budget.get("limits", {})
    max_runs = limits.get("max_worker_runs")
    max_tokens = limits.get("max_tokens")
    max_wall_time = limits.get("max_wall_time_seconds")
    max_graph_nodes = limits.get("max_graph_nodes")
    if max_runs is not None and usage.get("worker_runs", 0) >= max_runs:
        return True
    if max_tokens is not None and usage.get("tokens", 0) + additional_tokens >= max_tokens:
        return True
    if max_wall_time is not None:
        created = project.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        elapsed = (utcnow() - created).total_seconds() + additional_seconds
        if elapsed >= max_wall_time:
            return True
    return (
        max_graph_nodes is not None
        and usage.get("graph_nodes", 0) + additional_graph_nodes >= max_graph_nodes
    )


async def _validate_output(
    session: AsyncSession,
    project: Project,
    context: OrchestratorContext,
    output: OrchestratorOutput,
) -> tuple[dict[str, GraphNode], dict[str, Intent]]:
    nodes = list(
        (await session.scalars(select(GraphNode).where(GraphNode.project_id == project.id))).all()
    )
    nodes_by_key = {node.entity_key: node for node in nodes}
    intents = list(
        (
            await session.scalars(
                select(Intent).where(Intent.project_id == project.id, Intent.status == "open")
            )
        ).all()
    )
    intents_by_id = {intent.id: intent for intent in intents}
    intent_ids = set(output.intents_to_close) | set(output.intents_to_deprioritize)
    unknown_intents = intent_ids - set(intents_by_id)
    if unknown_intents:
        raise OrchestratorOutputError(
            f"decision references non-open intent(s): {', '.join(sorted(unknown_intents))}"
        )

    for proposal in output.intents_to_create:
        missing = set(proposal.source_entity_keys) - set(nodes_by_key)
        if missing:
            raise OrchestratorOutputError(
                f"unknown source entity key(s): {', '.join(sorted(missing))}"
            )
        description = normalize_intent(proposal.description)
        if description in VAGUE_INTENTS or VAGUE_INTENT_PATTERN.fullmatch(description):
            raise OrchestratorOutputError("intent description is too vague to admit")
    return nodes_by_key, intents_by_id


async def _has_supported_conclusion(session: AsyncSession, project_id: str) -> bool:
    evidence_node = aliased(GraphNode)
    return bool(
        await session.scalar(
            select(GraphNode.id)
            .join(
                GraphEdge,
                (GraphEdge.source_node_id == GraphNode.id)
                & (GraphEdge.kind == "verified_by")
                & (GraphEdge.project_id == project_id),
            )
            .join(
                evidence_node,
                GraphEdge.target_node_id == evidence_node.id,
            )
            .where(
                GraphNode.project_id == project_id,
                GraphNode.kind.in_(["Fact", "Conclusion"]),
                evidence_node.kind == "Evidence",
                evidence_node.project_id == project_id,
            )
            .limit(1)
        )
    )


async def _emit_failure(
    session: AsyncSession,
    project_id: str,
    run: OrchestratorRun,
    error: str,
    trigger: str,
) -> OrchestrationResult:
    project = await session.get(Project, project_id)
    if project is not None and (run.token_input or run.token_output):
        state = (project.config or {}).get("orchestrator", {})
        if not isinstance(state, dict):
            state = {}
        token_usage = state.get("token_usage", 0)
        if type(token_usage) is not int or token_usage < 0:
            token_usage = 0
        project.config = {
            **(project.config or {}),
            "orchestrator": {
                **state,
                "token_usage": token_usage + run.token_input + run.token_output,
            },
        }
    await emit_event(
        session,
        project_id,
        "orchestrator.failed",
        {
            "trigger": trigger,
            "error": error,
            "schema_valid": run.schema_valid,
            "retry_count": run.retry_count,
            "schema_invalid_attempts": run.schema_invalid_attempts,
            "token_input": run.token_input,
            "token_output": run.token_output,
            "duration_seconds": round(run.duration_seconds, 6),
            "diagnostics": {"stdout": run.stdout, "stderr": run.stderr},
        },
    )
    await session.commit()
    return OrchestrationResult(
        status="failed",
        token_input=run.token_input,
        token_output=run.token_output,
        retry_count=run.retry_count,
        error=error,
    )


async def trigger_after_worker_runs(
    session: AsyncSession,
    project_id: str,
    worker_run_ids: list[str],
    *,
    trigger: str = "worker_runs",
) -> OrchestrationResult | None:
    """Coalesce meaningful completions into one Pi decision; no-op without Pi configured."""
    if not get_settings().pi_command or not worker_run_ids:
        return None
    runs = list(
        (
            await session.scalars(
                select(WorkerRun)
                .join(Intent, Intent.id == WorkerRun.intent_id)
                .where(WorkerRun.id.in_(worker_run_ids), Intent.project_id == project_id)
            )
        ).all()
    )
    if not runs:
        return None
    meaningful = any(
        run.status == "failed"
        or any(
            (run.output_summary or {}).get(f"output_{name}_count", 0) > 0
            for name in ("observations", "evidence", "hypotheses", "facts", "suggested_intents")
        )
        for run in runs
    )
    open_count = await session.scalar(
        select(func.count(Intent.id)).where(
            Intent.project_id == project_id, Intent.status == "open"
        )
    )
    if not meaningful and open_count:
        return None
    return await orchestrate_project(session, project_id, trigger=trigger)


async def orchestrate_project(
    session: AsyncSession,
    project_id: str,
    *,
    trigger: str = "manual",
    driver: Any | None = None,
) -> OrchestrationResult:
    project = await session.get(Project, project_id)
    if project is None:
        raise ValueError("project not found")
    try:
        context = await assemble_orchestrator_context(session, project_id)
    except Exception as exc:
        run = OrchestratorRun(None, 0.0, error=str(exc))
        return await _emit_failure(
            session, project_id, run, run.error or "context assembly failed", trigger
        )
    if _budget_exhausted(context, project):
        project.status = "paused"
        await emit_event(
            session,
            project_id,
            "orchestrator.budget_exhausted",
            {"budget": context.budget},
        )
        await session.commit()
        return OrchestrationResult(status="paused", error="project budget exhausted")
    try:
        selected_driver = driver or get_orchestrator_driver()
        run: OrchestratorRun = await selected_driver.run_orchestrator(context)
    except Exception as exc:
        run = OrchestratorRun(None, 0.0, error=str(exc))
    if run.output is None:
        return await _emit_failure(
            session, project_id, run, run.error or "orchestrator returned no output", trigger
        )

    try:
        nodes_by_key, intents_by_id = await _validate_output(session, project, context, run.output)
    except OrchestratorOutputError as exc:
        return await _emit_failure(session, project_id, run, str(exc), trigger)

    output = run.output
    budget_limits = context.budget.get("limits", {})
    max_total_intents = int(budget_limits.get("max_intents", DEFAULT_MAX_PROJECT_INTENTS))
    max_open_intents = int(budget_limits.get("max_open_intents", DEFAULT_MAX_OPEN_INTENTS))
    max_graph_nodes = budget_limits.get("max_graph_nodes")
    current_graph_nodes = int(context.budget.get("usage", {}).get("graph_nodes", 0))
    current_total = int(context.budget.get("usage", {}).get("intents", 0))
    current_open = len(intents_by_id)
    budget_blocked = _budget_exhausted(
        context,
        project,
        additional_tokens=run.token_input + run.token_output,
        additional_seconds=run.duration_seconds,
    )

    closed = 0
    for intent_id in dict.fromkeys(output.intents_to_close):
        intent = intents_by_id[intent_id]
        intent.status = "closed"
        intent.completed_at = utcnow()
        intent.lease_until = None
        node = await session.get(GraphNode, intent.metadata_json.get("exploration_node_id"))
        if node:
            node.status = "closed"
            node.properties = {**node.properties, "status": "closed"}
        closed += 1

    deprioritized = 0
    for intent_id in dict.fromkeys(output.intents_to_deprioritize):
        intent = intents_by_id[intent_id]
        if intent_id in output.intents_to_close:
            continue
        if not intent.metadata_json.get("orchestrator_deprioritized"):
            intent.priority = max(0.01, round(intent.priority * 0.5, 4))
            intent.metadata_json = {
                **intent.metadata_json,
                "orchestrator_deprioritized": True,
            }
            node = await session.get(GraphNode, intent.metadata_json.get("exploration_node_id"))
            if node:
                node.properties = {**node.properties, "priority": intent.priority}
            deprioritized += 1

    created = 0
    duplicate_intents = 0
    proposals_seen: set[tuple[str, ...]] = set()
    admitted_proposals = output.intents_to_create[:MAX_NEW_INTENTS_PER_TICK]
    for proposal in admitted_proposals:
        if budget_blocked or current_total + created >= max_total_intents:
            continue
        if current_open - closed + created >= max_open_intents:
            continue
        if max_graph_nodes is not None and current_graph_nodes + created >= max_graph_nodes:
            continue
        source_keys = list(dict.fromkeys(proposal.source_entity_keys))
        source_ids = [nodes_by_key[key].id for key in source_keys]
        signature = (normalize_intent(proposal.description), *sorted(source_ids))
        if signature in proposals_seen:
            duplicate_intents += 1
            continue
        proposals_seen.add(signature)
        dedupe_key = intent_key(proposal.description, source_ids)
        existing_id = await session.scalar(
            select(Intent.id).where(
                Intent.project_id == project_id,
                Intent.dedupe_key == dedupe_key,
            )
        )
        await create_intent(
            session,
            project_id,
            IntentCreate(
                description=proposal.description.strip(),
                source_node_ids=source_ids,
                creator="orchestrator:pi",
                signals=PrioritySignals(
                    goal_relevance=proposal.goal_relevance,
                    information_gain=proposal.information_gain,
                    novelty=proposal.novelty,
                    confidence=proposal.confidence,
                    expected_cost=proposal.expected_cost,
                ),
                metadata={"reason": proposal.reason, "orchestrator_focus": output.focus},
            ),
        )
        if existing_id is None:
            created += 1
        else:
            duplicate_intents += 1

    # Consume exactly the proposal IDs observed by this context; a later Worker update is kept.
    current_state = (project.config or {}).get("orchestrator", {})
    if not isinstance(current_state, dict):
        current_state = {}
    current_pending = current_state.get("pending_worker_proposals", [])
    if not isinstance(current_pending, list):
        current_pending = []
    token_usage = current_state.get("token_usage", 0)
    if type(token_usage) is not int or token_usage < 0:
        token_usage = 0
    seen_ids = {
        item.get("proposal_id")
        for item in context.pending_worker_proposals
        if isinstance(item, dict)
    }
    remaining = [
        item
        for item in current_pending
        if not isinstance(item, dict) or item.get("proposal_id") not in seen_ids
    ]
    project.config = {
        **(project.config or {}),
        "orchestrator": {
            **current_state,
            "pending_worker_proposals": remaining,
            "last_state_summary": output.state_summary,
            "last_focus": output.focus,
            "token_usage": token_usage + run.token_input + run.token_output,
        },
    }

    remaining_open = current_open - closed + created
    budget_blocked = _budget_exhausted(
        context,
        project,
        additional_tokens=run.token_input + run.token_output,
        additional_seconds=run.duration_seconds,
        additional_graph_nodes=created,
    )
    convergence = output.convergence_status
    if convergence == "completed":
        has_conclusion = await _has_supported_conclusion(session, project_id)
        if context.critical_unknowns or output.critical_unknowns or not has_conclusion:
            convergence = "continue"
    elif convergence == "stalled" and remaining_open:
        convergence = "continue"

    if budget_blocked:
        project.status = "paused"
    elif convergence == "completed":
        project.status = "completed"
    elif convergence == "stalled":
        project.status = "stalled"
    else:
        project.status = "running"

    await emit_event(
        session,
        project_id,
        "orchestrator.completed",
        {
            "trigger": trigger,
            "schema_valid": run.schema_valid,
            "retry_count": run.retry_count,
            "schema_invalid_attempts": run.schema_invalid_attempts,
            "duration_seconds": round(run.duration_seconds, 6),
            "token_input": run.token_input,
            "token_output": run.token_output,
            "created_intents": created,
            "duplicate_intent_count": duplicate_intents,
            "duplicate_intent_rate": (
                duplicate_intents / len(admitted_proposals) if admitted_proposals else 0.0
            ),
            "closed_intents": closed,
            "deprioritized_intents": deprioritized,
            "pending_worker_proposals": len(context.pending_worker_proposals),
            "output_intents_to_create": len(output.intents_to_create),
            "convergence_status": convergence,
            "convergence_reason": output.convergence_reason,
            "focus": output.focus,
            "budget_blocked": budget_blocked,
            "output": output.model_dump(),
        },
    )
    await session.commit()
    return OrchestrationResult(
        status="paused" if budget_blocked else convergence,
        created_intents=created,
        closed_intents=closed,
        deprioritized_intents=deprioritized,
        token_input=run.token_input,
        token_output=run.token_output,
        retry_count=run.retry_count,
        error="budget exhausted" if budget_blocked else None,
    )
