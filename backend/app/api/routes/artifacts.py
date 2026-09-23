from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Artifact, Binary
from app.schemas import ArtifactRead, BinaryRead
from app.services.artifacts import ingest_binary, resolve_artifact_path

router = APIRouter()


@router.get("/projects/{project_id}/binaries", response_model=list[BinaryRead])
async def list_binaries(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[Binary]:
    return list(
        (await session.scalars(select(Binary).where(Binary.project_id == project_id))).all()
    )


@router.post(
    "/projects/{project_id}/binaries",
    response_model=BinaryRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_binary(
    project_id: str,
    file: UploadFile = File(...),
    authorization_basis: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Binary:
    try:
        binary = await ingest_binary(session, project_id, file, authorization_basis)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return binary


@router.get("/projects/{project_id}/artifacts", response_model=list[ArtifactRead])
async def list_artifacts(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[Artifact]:
    return list(
        (await session.scalars(select(Artifact).where(Artifact.project_id == project_id))).all()
    )


@router.get("/artifacts/{artifact_id}")
async def download_artifact(
    artifact_id: str, session: AsyncSession = Depends(get_session)
) -> FileResponse:
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        path = resolve_artifact_path(artifact.path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="artifact file not found") from exc
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
