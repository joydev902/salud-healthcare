import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, SessionDep
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.models import UserRole
from app.schemas.admin import ProviderAssignmentUpdate, UserCreate, UserOut, UserPage, UserUpdate
from app.schemas.auth import ProviderRef
from app.services import users

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=UserPage)
async def list_users(
    _: AdminUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> UserPage:
    return await users.list_users(
        session,
        q=(q or "").strip() or None,
        role=role,
        is_active=is_active,
        limit=limit,
        cursor=cursor,
    )


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, admin: AdminUser, session: SessionDep) -> UserOut:
    return await users.create_user(session, admin, body)


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: uuid.UUID, _: AdminUser, session: SessionDep) -> UserOut:
    return await users.get_user(session, user_id)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, admin: AdminUser, session: SessionDep
) -> UserOut:
    return await users.update_user(session, admin, user_id, body)


@router.get("/users/{user_id}/providers", response_model=list[ProviderRef])
async def get_assignments(
    user_id: uuid.UUID, _: AdminUser, session: SessionDep
) -> list[ProviderRef]:
    return (await users.get_user(session, user_id)).providers


@router.put("/users/{user_id}/providers", response_model=list[ProviderRef])
async def replace_assignments(
    user_id: uuid.UUID, body: ProviderAssignmentUpdate, admin: AdminUser, session: SessionDep
) -> list[ProviderRef]:
    return await users.replace_assignments(session, admin, user_id, body.provider_ids)


@router.get("/providers", response_model=list[ProviderRef])
async def list_all_providers(_: AdminUser, session: SessionDep) -> list[ProviderRef]:
    return await users.all_providers(session)
