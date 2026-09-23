from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import GraphNode
from app.schemas import EdgeCreate, EdgeRead, GraphSnapshot, NodeCreate, NodeRead
from app.services.graph import get_neighborhood, get_snapshot, upsert_edge, upsert_node

router = APIRouter()


@router.get("/projects/{project_id}/graph", response_model=GraphSnapshot)
async def graph_snapshot(
    project_id: str,
    graph_type: str | None = Query(default=None, pattern="^(exploration|program|evidence)$"),
    session: AsyncSession = Depends(get_session),
) -> GraphSnapshot:
    return await get_snapshot(session, project_id, graph_type)


@router.post(
    "/projects/{project_id}/nodes", response_model=NodeRead, status_code=status.HTTP_201_CREATED
)
async def create_node(
    project_id: str, data: NodeCreate, session: AsyncSession = Depends(get_session)
) -> GraphNode:
    node = await upsert_node(session, project_id, data)
    await session.commit()
    return node


@router.post(
    "/projects/{project_id}/edges", response_model=EdgeRead, status_code=status.HTTP_201_CREATED
)
async def create_edge(
    project_id: str, data: EdgeCreate, session: AsyncSession = Depends(get_session)
):
    edge = await upsert_edge(session, project_id, data)
    await session.commit()
    return edge


@router.get("/nodes/{node_id}", response_model=NodeRead)
async def get_node(node_id: str, session: AsyncSession = Depends(get_session)) -> GraphNode:
    node = await session.get(GraphNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node


@router.get("/nodes/{node_id}/neighbors", response_model=GraphSnapshot)
async def node_neighbors(
    node_id: str,
    hops: int = Query(default=1, ge=1, le=2),
    session: AsyncSession = Depends(get_session),
) -> GraphSnapshot:
    snapshot = await get_neighborhood(session, node_id, hops=hops)
    if not snapshot.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return snapshot
