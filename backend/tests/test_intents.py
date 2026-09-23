from app.models import Project, Worker
from app.schemas import IntentCreate, PrioritySignals
from app.services.intents import claim_next_intent, create_intent, score_intent


async def test_intent_priority_deduplication_and_claim(session):
    project = Project(name="case", goal="find validation")
    session.add(project)
    await session.flush()
    worker = Worker(project_id=project.id, name="worker-01")
    session.add(worker)
    await session.flush()

    payload = IntentCreate(
        description="Inspect validation function",
        signals=PrioritySignals(
            goal_relevance="high",
            information_gain="high",
            confidence="high",
            expected_cost="low",
        ),
    )
    first = await create_intent(session, project.id, payload)
    second = await create_intent(session, project.id, payload)

    assert first.id == second.id
    assert score_intent(payload) == 1.0

    claimed = await claim_next_intent(session, project.id, worker.id)
    assert claimed is not None
    assert claimed.id == first.id
    assert claimed.status == "claimed"
    assert claimed.worker_id == worker.id
    assert claimed.lease_until is not None
