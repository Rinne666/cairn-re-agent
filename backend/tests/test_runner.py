from sqlalchemy import func, select

from app.models import GraphEdge, GraphNode, Intent, Worker
from app.services.runner import run_once, seed_demo


async def test_worker_run_extends_evidence_graph_and_queue(session):
    project = await seed_demo(session)
    await session.flush()
    worker = await session.scalar(select(Worker).where(Worker.project_id == project.id))
    assert worker is not None

    result = await run_once(session, project.id, worker.id)

    assert result is not None
    assert result.status == "completed"
    assert result.created_nodes == 3
    assert result.created_intents == 1

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
    assert open_intents == 1
