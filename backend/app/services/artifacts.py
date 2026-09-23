import hashlib
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Artifact, Binary
from app.services.events import emit_event

ALLOWED_AUTHORIZATION_BASES = {"owner_provided_sample", "ctf", "lab"}


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "sample.bin").name
    return "".join(character for character in name if character.isalnum() or character in "._-")[
        :180
    ]


async def ingest_binary(
    session: AsyncSession,
    project_id: str,
    upload: UploadFile,
    authorization_basis: str,
) -> Binary:
    if authorization_basis not in ALLOWED_AUTHORIZATION_BASES:
        raise ValueError("authorization_basis must be owner_provided_sample, ctf, or lab")
    settings = get_settings()
    limit = settings.max_upload_mb * 1024 * 1024
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"sample exceeds {settings.max_upload_mb} MiB limit")
    if not data:
        raise ValueError("sample is empty")

    digest = hashlib.sha256(data).hexdigest()
    sample_dir = settings.artifact_root.resolve() / project_id / "binaries"
    sample_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(upload.filename)
    path = sample_dir / f"{digest[:12]}-{filename}"
    path.write_bytes(data)

    binary = Binary(
        project_id=project_id,
        filename=filename,
        path=str(path),
        sha256=digest,
        metadata_json={
            "authorization_basis": authorization_basis,
            "content_type": upload.content_type,
            "analysis_status": "not_started",
        },
    )
    session.add(binary)
    await session.flush()
    artifact = Artifact(
        project_id=project_id,
        kind="binary",
        path=str(path),
        sha256=digest,
        size=len(data),
        summary=f"Authorized local sample: {filename}",
        provenance={
            "operation": "binary.ingest",
            "authorization_basis": authorization_basis,
        },
    )
    session.add(artifact)
    await session.flush()
    await emit_event(
        session,
        project_id,
        "binary.created",
        {"binary_id": binary.id, "artifact_id": artifact.id, "sha256": digest},
    )
    return binary


def resolve_artifact_path(path: str) -> Path:
    root = get_settings().artifact_root.resolve()
    resolved = Path(path).resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("artifact path escapes configured root")
    if not resolved.is_file():
        raise FileNotFoundError(path)
    return resolved
