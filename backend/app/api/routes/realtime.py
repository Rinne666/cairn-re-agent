import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Event
from app.schemas import EventRead
from app.services.events import broker

router = APIRouter()


@router.get("/projects/{project_id}/events", response_model=list[EventRead])
async def list_events(
    project_id: str, limit: int = 100, session: AsyncSession = Depends(get_session)
) -> list[Event]:
    events = list(
        (
            await session.scalars(
                select(Event)
                .where(Event.project_id == project_id)
                .order_by(Event.created_at.desc())
                .limit(min(max(limit, 1), 500))
            )
        ).all()
    )
    return list(reversed(events))


@router.websocket("/projects/{project_id}/events")
async def project_events(websocket: WebSocket, project_id: str) -> None:
    await websocket.accept()
    queue = broker.subscribe(project_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=25)
                await websocket.send_json(event)
            except TimeoutError:
                await websocket.send_json({"kind": "heartbeat", "project_id": project_id})
    except WebSocketDisconnect:
        pass
    finally:
        broker.unsubscribe(project_id, queue)
