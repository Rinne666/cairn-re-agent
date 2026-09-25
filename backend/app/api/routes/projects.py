from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import Project
from app.schemas import ProjectCreate, ProjectRead
from app.services.events import emit_event
from app.services.orchestrator import orchestrate_project
from app.services.runner import seed_demo

router = APIRouter()


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[Project]:
    return list((await session.scalars(select(Project).order_by(Project.updated_at.desc()))).all())


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate, session: AsyncSession = Depends(get_session)
) -> Project:
    project = Project(name=data.name, goal=data.goal, config=data.config)
    session.add(project)
    await session.flush()
    await emit_event(session, project.id, "project.created", {"project_id": project.id})
    await session.commit()
    if get_settings().pi_command:
        await orchestrate_project(session, project.id, trigger="project_created")
    return project


@router.post("/demo", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_demo_project(session: AsyncSession = Depends(get_session)) -> Project:
    project = await seed_demo(session)
    await session.commit()
    if get_settings().pi_command:
        await orchestrate_project(session, project.id, trigger="project_created")
    return project


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, session: AsyncSession = Depends(get_session)) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


async def _change_project_state(project_id: str, action: str, session: AsyncSession) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    project.status = "running" if action == "start" else "paused"
    await emit_event(session, project.id, f"project.{action}d", {"project_id": project.id})
    await session.commit()
    return project


@router.post("/{project_id}/start", response_model=ProjectRead)
async def start_project(project_id: str, session: AsyncSession = Depends(get_session)) -> Project:
    return await _change_project_state(project_id, "start", session)


@router.post("/{project_id}/pause", response_model=ProjectRead)
async def pause_project(project_id: str, session: AsyncSession = Depends(get_session)) -> Project:
    return await _change_project_state(project_id, "pause", session)
