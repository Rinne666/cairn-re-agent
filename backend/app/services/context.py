from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GraphNode, Intent, IntentSource, Project
from app.services.graph import get_neighborhood
from app.worker_protocol import WorkerContext


async def assemble_context(session: AsyncSession, intent: Intent) -> WorkerContext:
    project = await session.get(Project, intent.project_id)
    if project is None:
        raise ValueError("project not found")
    source_ids = list(
        (
            await session.scalars(
                select(IntentSource.node_id).where(IntentSource.intent_id == intent.id)
            )
        ).all()
    )
    nearby: dict[str, GraphNode] = {}
    for source_id in source_ids[:5]:
        snapshot = await get_neighborhood(session, source_id, hops=2, limit=60)
        nearby.update({node.id: node for node in snapshot.nodes})

    def pack(node: GraphNode) -> dict:
        return {
            "id": node.id,
            "kind": node.kind,
            "label": node.label,
            "entity_key": node.entity_key,
            "confidence": node.confidence,
            "properties": node.properties,
        }

    nodes = list(nearby.values())
    return WorkerContext(
        goal=project.goal,
        intent=intent.description,
        facts=[pack(node) for node in nodes if node.kind in {"Fact", "Conclusion"}],
        program_nodes=[pack(node) for node in nodes if node.graph_type == "program"],
        evidence=[
            pack(node) for node in nodes if node.kind in {"Observation", "Evidence", "Trace"}
        ],
        hypotheses=[pack(node) for node in nodes if node.kind == "Hypothesis"],
        failed_directions=[],
        available_tools=["get_binary_info", "list_functions", "decompile_function", "get_xrefs"],
        budget=project.config.get("budget", {"max_tool_calls": 12, "max_tokens": 16000}),
    )
