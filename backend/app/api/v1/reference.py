"""Filter options. Providers, initiatives and years are limited to the caller's scope."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.auth import ProviderRef
from app.schemas.queue import PayerRef
from app.services import access, queue

router = APIRouter(tags=["reference data"])


@router.get("/providers", response_model=list[ProviderRef])
async def list_providers(user: CurrentUser, session: SessionDep) -> list[ProviderRef]:
    providers = await access.assigned_providers(session, user.id)
    return [ProviderRef(id=p.id, name=p.display_name, group_name=g.name) for p, g in providers]


@router.get("/payers", response_model=list[PayerRef])
async def list_payers(_: CurrentUser, session: SessionDep) -> list[PayerRef]:
    return await queue.payers(session)


@router.get("/initiatives", response_model=list[str])
async def list_initiatives(user: CurrentUser, session: SessionDep) -> list[str]:
    return await queue.initiatives(session, user)


@router.get("/performance-years", response_model=list[int])
async def list_performance_years(user: CurrentUser, session: SessionDep) -> list[int]:
    return await queue.performance_years(session, user)
