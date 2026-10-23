import uuid

from fastapi import APIRouter

from app.api.deps import CoderUser, CurrentUser, SessionDep
from app.schemas.dispositions import DispositionHistoryItem, DispositionRequest, DispositionResult
from app.schemas.queue import OpportunityDetail
from app.services import dispositions, queue

router = APIRouter(prefix="/opportunities", tags=["work queue"])


@router.get("/{opportunity_id}", response_model=OpportunityDetail)
async def get_opportunity(
    opportunity_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> OpportunityDetail:
    return await queue.get_opportunity(session, user, opportunity_id)


@router.post("/{opportunity_id}/dispositions", response_model=DispositionResult)
async def record_disposition(
    opportunity_id: uuid.UUID, body: DispositionRequest, coder: CoderUser, session: SessionDep
) -> DispositionResult:
    return await dispositions.record_disposition(session, coder, opportunity_id, body)


@router.get("/{opportunity_id}/dispositions", response_model=list[DispositionHistoryItem])
async def disposition_history(
    opportunity_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[DispositionHistoryItem]:
    return await dispositions.history(session, user, opportunity_id)
