import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, SessionDep
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.models import Disposition
from app.schemas.queue import MemberDetail, MemberPage, OpportunitySummary
from app.services import queue
from app.services.queue import OpportunityFilters

router = APIRouter(prefix="/members", tags=["work queue"])


def opportunity_filters(
    provider_id: int | None = None,
    payer_id: int | None = None,
    initiative: Annotated[str | None, Query(max_length=64)] = None,
    disposition: Annotated[list[Disposition] | None, Query()] = None,
    performance_year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> OpportunityFilters:
    return OpportunityFilters(
        provider_id=provider_id,
        payer_id=payer_id,
        initiative=initiative or None,
        dispositions=tuple(sorted(set(disposition or ()))),
        performance_year=performance_year,
    )


FiltersDep = Annotated[OpportunityFilters, Depends(opportunity_filters)]


@router.get("", response_model=MemberPage)
async def list_members(
    user: CurrentUser,
    session: SessionDep,
    filters: FiltersDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> MemberPage:
    return await queue.list_members(
        session, user, filters, q=(q or "").strip() or None, limit=limit, cursor=cursor
    )


@router.get("/{member_id}", response_model=MemberDetail)
async def get_member(member_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> MemberDetail:
    return await queue.get_member(session, user, member_id)


@router.get("/{member_id}/opportunities", response_model=list[OpportunitySummary])
async def list_member_opportunities(
    member_id: uuid.UUID, user: CurrentUser, session: SessionDep, filters: FiltersDep
) -> list[OpportunitySummary]:
    return await queue.list_member_opportunities(session, user, member_id, filters)
