import asyncio

from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Intent, Worker
from app.schemas import RunResult
from app.services.runner import run_once


async def _run_worker(project_id: str, worker_id: str) -> RunResult | None:
    async with SessionLocal() as session:
        try:
            result = await run_once(session, project_id, worker_id)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


async def scheduler_tick(project_id: str) -> list[RunResult]:
    """Claim and execute up to max_workers intents with isolated transactions."""
    async with SessionLocal() as session:
        open_count = await session.scalar(
            select(func.count(Intent.id)).where(
                Intent.project_id == project_id, Intent.status == "open"
            )
        )
        workers = list(
            (
                await session.scalars(
                    select(Worker)
                    .where(Worker.project_id == project_id, Worker.status == "idle")
                    .order_by(Worker.created_at)
                    .limit(min(get_settings().max_workers, open_count or 0))
                )
            ).all()
        )
    if not workers:
        return []
    results = await asyncio.gather(
        *(_run_worker(project_id, worker.id) for worker in workers), return_exceptions=True
    )
    return [result for result in results if isinstance(result, RunResult)]
