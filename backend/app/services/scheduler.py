import asyncio

from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Intent, Project, Worker
from app.schemas import RunResult
from app.services.orchestrator import trigger_after_worker_runs
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
        project = await session.get(Project, project_id)
        if project is None or project.status != "running":
            return []
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
    completed_runs = [result for result in results if isinstance(result, RunResult)]
    if completed_runs:
        async with SessionLocal() as session:
            await trigger_after_worker_runs(
                session,
                project_id,
                [result.worker_run_id for result in completed_runs],
                trigger="scheduler_tick",
            )
    return completed_runs
