from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Intent, Worker, utcnow
from app.schemas import ClaimRequest, CompleteRequest, IntentCreate, IntentRead
from app.services.events import emit_event
from app.services.intents import create_intent, heartbeat

router = APIRouter()


@router.get("/projects/{project_id}/intents", response_model=list[IntentRead])
async def list_intents(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[Intent]:
    return list(
        (
            await session.scalars(
                select(Intent)
                .where(Intent.project_id == project_id)
                .order_by(Intent.status, Intent.priority.desc())
            )
        ).all()
    )


@router.post(
    "/projects/{project_id}/intents", response_model=IntentRead, status_code=status.HTTP_201_CREATED
)
async def post_intent(
    project_id: str, data: IntentCreate, session: AsyncSession = Depends(get_session)
) -> Intent:
    intent = await create_intent(session, project_id, data)
    await session.commit()
    return intent


@router.post("/intents/{intent_id}/heartbeat", response_model=IntentRead)
async def post_heartbeat(
    intent_id: str, data: ClaimRequest, session: AsyncSession = Depends(get_session)
) -> Intent:
    intent = await session.get(Intent, intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="intent not found")
    try:
        await heartbeat(session, intent, data.worker_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return intent


@router.post("/intents/{intent_id}/complete", response_model=IntentRead)
async def complete_intent(
    intent_id: str, data: CompleteRequest, session: AsyncSession = Depends(get_session)
) -> Intent:
    intent = await session.get(Intent, intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="intent not found")
    if intent.worker_id != data.worker_id:
        raise HTTPException(status_code=409, detail="intent is not leased by this worker")
    intent.status = data.status
    intent.result_node_id = data.result_node_id
    intent.completed_at = utcnow()
    worker = await session.get(Worker, data.worker_id)
    if worker:
        worker.status = "idle"
    await emit_event(
        session,
        intent.project_id,
        f"intent.{data.status}",
        {"intent_id": intent.id, "result_node_id": data.result_node_id, "error": data.error},
    )
    await session.commit()
    return intent
