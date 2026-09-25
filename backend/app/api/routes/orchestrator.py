from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.schemas import OrchestrationRead
from app.services.orchestrator import orchestrate_project

router = APIRouter()


@router.post("/projects/{project_id}/orchestrate", response_model=OrchestrationRead)
async def run_orchestrator(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> OrchestrationRead:
    if not get_settings().pi_command:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph Orchestrator requires CAIRN_PI_COMMAND",
        )
    try:
        result = await orchestrate_project(session, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OrchestrationRead(**result.__dict__)
