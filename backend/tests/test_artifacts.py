import hashlib
from io import BytesIO

import pytest
from fastapi import UploadFile

from app.config import get_settings
from app.services.artifacts import ingest_binary, resolve_artifact_path


async def test_binary_ingest_records_hash_authorization_and_artifact(session, tmp_path):
    settings = get_settings()
    original_root = settings.artifact_root
    settings.artifact_root = tmp_path
    try:
        from app.models import Project

        project = Project(name="sample", goal="inspect owned crackme")
        session.add(project)
        await session.flush()
        upload = UploadFile(filename="crackme.exe", file=BytesIO(b"MZ\x00demo"))

        binary = await ingest_binary(session, project.id, upload, "owner_provided_sample")

        assert binary.sha256 == hashlib.sha256(b"MZ\x00demo").hexdigest()
        assert binary.metadata_json["analysis_status"] == "not_started"
        assert resolve_artifact_path(binary.path).read_bytes() == b"MZ\x00demo"
    finally:
        settings.artifact_root = original_root


async def test_binary_ingest_rejects_missing_authorization_basis(session):
    upload = UploadFile(filename="sample.bin", file=BytesIO(b"data"))
    with pytest.raises(ValueError, match="authorization_basis"):
        await ingest_binary(session, "unused", upload, "unknown")
