"""Disposition changes and their append-only audit trail.

A change locks the opportunity row, verifies the caller's expected version, then writes
the history record and the new current state in one transaction: either both persist or
neither does.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.models import DispositionHistory, Opportunity, User
from app.schemas.dispositions import DispositionHistoryItem, DispositionRequest, DispositionResult
from app.services import access


async def record_disposition(
    session: AsyncSession, user: User, opportunity_id: uuid.UUID, request: DispositionRequest
) -> DispositionResult:
    allowed = await access.assigned_provider_ids(session, user.id)
    opp = await session.scalar(
        select(Opportunity)
        .where(Opportunity.id == opportunity_id, Opportunity.provider_id.in_(allowed))
        .with_for_update()
    )
    if opp is None:
        raise NotFoundError("Opportunity not found")
    if opp.disposition_version != request.expected_version:
        changed_by = await session.scalar(
            select(User.email).where(User.id == opp.last_disposition_by)
        )
        raise AppError(
            409,
            "STALE_VERSION",
            "This opportunity was updated by someone else. Review the latest decision and "
            "submit again if it still applies.",
            {
                "current_disposition": opp.current_disposition,
                "disposition_version": opp.disposition_version,
                "last_disposition_at": (
                    opp.last_disposition_at.isoformat() if opp.last_disposition_at else None
                ),
                "last_disposition_by_email": changed_by,
            },
        )

    now = datetime.now(UTC)
    session.add(
        DispositionHistory(
            opportunity_id=opp.id,
            changed_by=user.id,
            changed_at=now,
            old_status=opp.current_disposition,
            new_status=request.new_disposition,
            note=request.justification,
            old_version=opp.disposition_version,
            new_version=opp.disposition_version + 1,
        )
    )
    opp.current_disposition = request.new_disposition
    opp.current_note = request.justification
    opp.disposition_version += 1
    opp.last_disposition_at = now
    opp.last_disposition_by = user.id
    await session.commit()

    return DispositionResult(
        opportunity_id=opp.id,
        current_disposition=opp.current_disposition,
        disposition_version=opp.disposition_version,
        changed_at=now,
    )


async def history(
    session: AsyncSession, user: User, opportunity_id: uuid.UUID
) -> list[DispositionHistoryItem]:
    allowed = await access.assigned_provider_ids(session, user.id)
    visible = await session.scalar(
        select(Opportunity.id).where(
            Opportunity.id == opportunity_id, Opportunity.provider_id.in_(allowed)
        )
    )
    if visible is None:
        raise NotFoundError("Opportunity not found")

    rows = await session.execute(
        select(DispositionHistory, User.email, User.full_name)
        .join(User, User.id == DispositionHistory.changed_by)
        .where(DispositionHistory.opportunity_id == opportunity_id)
        .order_by(DispositionHistory.changed_at.desc(), DispositionHistory.id.desc())
    )
    return [
        DispositionHistoryItem(
            id=h.id,
            changed_at=h.changed_at,
            changed_by_email=email,
            changed_by_name=name,
            old_status=h.old_status,
            new_status=h.new_status,
            note=h.note,
            old_version=h.old_version,
            new_version=h.new_version,
        )
        for h, email, name in rows
    ]
