import re
from collections import deque

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GraphEdge, GraphNode
from app.schemas import EdgeCreate, GraphSnapshot, NodeCreate
from app.services.events import emit_event

ADDRESS_ENTITY_KINDS = {"Function", "BasicBlock", "String", "Constant", "API", "Variable"}


def _canonical_address(value: object) -> str | None:
    if isinstance(value, int):
        return format(value, "x")
    if not isinstance(value, str):
        return None
    address = value.strip().lower()
    if address.startswith("0x"):
        address = address[2:]
    address = re.sub(r"^0+(?=[0-9a-f])", "", address)
    return address or None


def _canonical_entity_key(project_id: str, data: NodeCreate) -> str:
    if data.kind in ADDRESS_ENTITY_KINDS:
        address = _canonical_address(data.properties.get("address"))
        if address:
            scope = data.binary_id or project_id
            return f"{data.kind.lower()}:{scope}:0x{address}"
    return data.entity_key


async def upsert_node(session: AsyncSession, project_id: str, data: NodeCreate) -> GraphNode:
    entity_key = _canonical_entity_key(project_id, data)
    node = await session.scalar(
        select(GraphNode).where(
            GraphNode.project_id == project_id, GraphNode.entity_key == entity_key
        )
    )
    if node is None and entity_key != data.entity_key and data.kind in ADDRESS_ENTITY_KINDS:
        address = _canonical_address(data.properties.get("address"))
        candidates = await session.scalars(
            select(GraphNode).where(
                GraphNode.project_id == project_id,
                GraphNode.kind == data.kind,
                GraphNode.binary_id == data.binary_id,
            )
        )
        node = next(
            (
                candidate
                for candidate in candidates
                if _canonical_address(candidate.properties.get("address")) == address
            ),
            None,
        )
        if node is not None:
            node.entity_key = entity_key

    created = node is None
    if node is None:
        node = GraphNode(
            project_id=project_id,
            **data.model_dump(exclude={"entity_key"}),
            entity_key=entity_key,
        )
        session.add(node)
    else:
        node.label = data.label
        node.properties = {**node.properties, **data.properties}
        node.confidence = max(node.confidence, data.confidence)
        node.status = data.status
    await session.flush()
    await emit_event(
        session,
        project_id,
        "node.created" if created else "node.updated",
        {"node_id": node.id, "graph_type": node.graph_type, "kind": node.kind},
    )
    return node


async def upsert_edge(session: AsyncSession, project_id: str, data: EdgeCreate) -> GraphEdge:
    edge = await session.scalar(
        select(GraphEdge).where(
            GraphEdge.project_id == project_id,
            GraphEdge.source_node_id == data.source_node_id,
            GraphEdge.target_node_id == data.target_node_id,
            GraphEdge.kind == data.kind,
        )
    )
    if edge is None:
        edge = GraphEdge(project_id=project_id, **data.model_dump())
        session.add(edge)
        await session.flush()
        await emit_event(
            session,
            project_id,
            "edge.created",
            {"edge_id": edge.id, "kind": edge.kind},
        )
    return edge


async def get_snapshot(
    session: AsyncSession, project_id: str, graph_type: str | None = None
) -> GraphSnapshot:
    node_query = select(GraphNode).where(GraphNode.project_id == project_id)
    if graph_type:
        node_query = node_query.where(GraphNode.graph_type == graph_type)
    nodes = list((await session.scalars(node_query.order_by(GraphNode.created_at))).all())
    node_ids = [node.id for node in nodes]
    if not node_ids:
        return GraphSnapshot(nodes=[], edges=[])
    edges = list(
        (
            await session.scalars(
                select(GraphEdge).where(
                    GraphEdge.project_id == project_id,
                    GraphEdge.source_node_id.in_(node_ids),
                    GraphEdge.target_node_id.in_(node_ids),
                )
            )
        ).all()
    )
    return GraphSnapshot(nodes=nodes, edges=edges)


async def get_neighborhood(
    session: AsyncSession, node_id: str, hops: int = 1, limit: int = 100
) -> GraphSnapshot:
    root = await session.get(GraphNode, node_id)
    if root is None:
        return GraphSnapshot(nodes=[], edges=[])
    visited = {root.id}
    frontier = deque([root.id])
    all_edges: dict[str, GraphEdge] = {}
    for _ in range(max(1, min(hops, 2))):
        if not frontier or len(visited) >= limit:
            break
        level = list(frontier)
        frontier.clear()
        result = await session.scalars(
            select(GraphEdge).where(
                GraphEdge.project_id == root.project_id,
                or_(GraphEdge.source_node_id.in_(level), GraphEdge.target_node_id.in_(level)),
            )
        )
        for edge in result:
            all_edges[edge.id] = edge
            for candidate in (edge.source_node_id, edge.target_node_id):
                if candidate not in visited and len(visited) < limit:
                    visited.add(candidate)
                    frontier.append(candidate)
    nodes = list((await session.scalars(select(GraphNode).where(GraphNode.id.in_(visited)))).all())
    return GraphSnapshot(nodes=nodes, edges=list(all_edges.values()))
