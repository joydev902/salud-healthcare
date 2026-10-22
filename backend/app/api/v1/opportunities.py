import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.queue import OpportunityDetail
from app.services import queue

router = APIRouter(prefix="/opportunities", tags=["work queue"])


@router.get("/{opportunity_id}", response_model=OpportunityDetail)
async def get_opportunity(
    opportunity_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> OpportunityDetail:
    return await queue.get_opportunity(session, user, opportunity_id)
