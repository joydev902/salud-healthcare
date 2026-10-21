import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile, status

from app.api.deps import AdminUser, SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.schemas.imports import ImportDetail, ImportPage
from app.services import import_history, ingestion

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("", response_model=ImportDetail, status_code=status.HTTP_201_CREATED)
async def upload_csv(
    admin: AdminUser, session: SessionDep, file: Annotated[UploadFile, File()]
) -> ImportDetail:
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith(".csv"):
        raise AppError(400, "INVALID_FILE", "Only .csv files are accepted")

    limit = get_settings().max_upload_bytes
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise AppError(
            413, "PAYLOAD_TOO_LARGE", f"File exceeds the {limit // (1024 * 1024)} MB upload limit"
        )
    if not content.strip():
        raise AppError(400, "INVALID_FILE", "File is empty")

    batch = await ingestion.import_csv(
        session, filename=filename, content=content, uploaded_by=admin.id
    )
    return await import_history.get_import(session, batch.id)


@router.get("", response_model=ImportPage)
async def list_imports(
    _: AdminUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> ImportPage:
    return await import_history.list_imports(session, limit=limit, cursor=cursor)


@router.get("/{upload_id}", response_model=ImportDetail)
async def get_import(upload_id: uuid.UUID, _: AdminUser, session: SessionDep) -> ImportDetail:
    return await import_history.get_import(session, upload_id)
