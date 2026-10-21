import uuid
from datetime import datetime

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.pagination import decode_cursor, encode_cursor
from app.models import UploadBatch, User
from app.schemas.imports import ImportDetail, ImportPage, ImportSummary


def _base_query() -> Select:
    return select(UploadBatch, User.email).join(User, User.id == UploadBatch.uploaded_by)


def _summary(batch: UploadBatch, email: str) -> ImportSummary:
    return ImportSummary(
        id=batch.id,
        filename=batch.uploaded_filename,
        sha256=batch.sha256,
        status=batch.status,
        uploaded_by_email=email,
        started_at=batch.started_at,
        finished_at=batch.finished_at,
        total_rows=batch.total_rows,
        inserted_source_rows=batch.inserted_rows,
        duplicate_source_rows=batch.duplicate_rows,
        rejected_rows=batch.rejected_rows,
        new_opportunities=batch.new_opportunities,
    )


async def list_imports(session: AsyncSession, *, limit: int, cursor: str | None) -> ImportPage:
    query = _base_query()
    if cursor:
        started_raw, id_raw = decode_cursor(cursor, 2)
        started, last_id = datetime.fromisoformat(started_raw), uuid.UUID(id_raw)
        query = query.where(
            or_(
                UploadBatch.started_at < started,
                and_(UploadBatch.started_at == started, UploadBatch.id < last_id),
            )
        )
    query = query.order_by(UploadBatch.started_at.desc(), UploadBatch.id.desc()).limit(limit + 1)
    rows = (await session.execute(query)).all()

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        encode_cursor([rows[-1][0].started_at.isoformat(), str(rows[-1][0].id)])
        if has_more
        else None
    )
    return ImportPage(
        items=[_summary(b, email) for b, email in rows], next_cursor=next_cursor, has_more=has_more
    )


async def get_import(session: AsyncSession, upload_id: uuid.UUID) -> ImportDetail:
    row = (await session.execute(_base_query().where(UploadBatch.id == upload_id))).first()
    if row is None:
        raise NotFoundError("Upload not found")
    batch, email = row
    return ImportDetail.from_summary(_summary(batch, email), batch.error_summary)
