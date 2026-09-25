from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Worker
from app.schemas import RunResult, WorkerCreate, WorkerRead
from app.services.orchestrator import trigger_after_worker_runs
from app.services.runner import run_once
from app.services.scheduler import scheduler_tick

router = APIRouter()


@router.get("/projects/{project_id}/workers", response_model=list[WorkerRead])
async def list_workers(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[Worker]:
    return list(
        (await session.scalars(select(Worker).where(Worker.project_id == project_id))).all()
    )


@router.post(
    "/projects/{project_id}/workers", response_model=WorkerRead, status_code=status.HTTP_201_CREATED
)
async def create_worker(
    project_id: str, data: WorkerCreate, session: AsyncSession = Depends(get_session)
) -> Worker:
    worker = Worker(
        project_id=project_id,
        name=data.name,
        driver=data.driver,
        model=data.model,
        metadata_json=data.metadata,
    )
    session.add(worker)
    await session.commit()
    return worker


@router.post("/projects/{project_id}/workers/{worker_id}/run-once", response_model=RunResult)
async def execute_worker(
    project_id: str, worker_id: str, session: AsyncSession = Depends(get_session)
) -> RunResult:
    try:
        result = await run_once(session, project_id, worker_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="no claimable intent")
    await session.commit()
    await trigger_after_worker_runs(
        session, project_id, [result.worker_run_id], trigger="worker_run"
    )
    return result


@router.post("/projects/{project_id}/scheduler/tick", response_model=list[RunResult])
async def tick_scheduler(project_id: str) -> list[RunResult]:
    return await scheduler_tick(project_id)
