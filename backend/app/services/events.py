import asyncio
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event


class EventBroker:
    """In-process fanout; the database event log remains the durable source."""

    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def subscribe(self, project_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._queues[project_id].add(queue)
        return queue

    def unsubscribe(self, project_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues[project_id].discard(queue)

    async def publish(self, project_id: str, message: dict[str, Any]) -> None:
        for queue in list(self._queues[project_id]):
            if queue.full():
                _ = queue.get_nowait()
            await queue.put(message)


broker = EventBroker()


async def emit_event(
    session: AsyncSession, project_id: str, kind: str, payload: dict[str, Any]
) -> Event:
    event = Event(project_id=project_id, kind=kind, payload=payload)
    session.add(event)
    await session.flush()
    await broker.publish(
        project_id,
        {
            "id": event.id,
            "project_id": project_id,
            "kind": kind,
            "payload": payload,
            "created_at": event.created_at.isoformat(),
        },
    )
    return event
