"""Provider-level authorization. Scope is always read from the database at request
time, never from the token, so revoking an assignment takes effect immediately.

Admins see every provider. Coders see only their assignments.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Provider, ProviderGroup, User, UserProviderAssignment, UserRole


async def visible_provider_ids(session: AsyncSession, user: User) -> set[int]:
    if user.role == UserRole.ADMIN:
        return set(await session.scalars(select(Provider.id)))
    return await assigned_provider_ids(session, user.id)


async def visible_providers(
    session: AsyncSession, user: User
) -> list[tuple[Provider, ProviderGroup]]:
    if user.role == UserRole.ADMIN:
        rows = await session.execute(
            select(Provider, ProviderGroup)
            .join(ProviderGroup, Provider.provider_group_id == ProviderGroup.id)
            .order_by(ProviderGroup.name, Provider.display_name)
        )
        return [(provider, group) for provider, group in rows]
    return await assigned_providers(session, user.id)


async def assigned_provider_ids(session: AsyncSession, user_id: uuid.UUID) -> set[int]:
    rows = await session.scalars(
        select(UserProviderAssignment.provider_id).where(UserProviderAssignment.user_id == user_id)
    )
    return set(rows)


async def assigned_providers(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Provider, ProviderGroup]]:
    rows = await session.execute(
        select(Provider, ProviderGroup)
        .join(ProviderGroup, Provider.provider_group_id == ProviderGroup.id)
        .join(UserProviderAssignment, UserProviderAssignment.provider_id == Provider.id)
        .where(UserProviderAssignment.user_id == user_id)
        .order_by(ProviderGroup.name, Provider.display_name)
    )
    return [(provider, group) for provider, group in rows]
