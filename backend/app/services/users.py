"""Admin user management: accounts, roles, activation and provider assignments.

Changes take effect on the user's next request because authorization is always read from
the database. Admins cannot deactivate or demote themselves, so the last admin cannot be
locked out by accident.
"""

import logging
import uuid
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.core.pagination import decode_cursor, encode_cursor
from app.core.security import hash_password
from app.models import Provider, ProviderGroup, User, UserProviderAssignment, UserRole
from app.schemas.admin import UserCreate, UserOut, UserPage, UserUpdate
from app.schemas.auth import ProviderRef
from app.services.normalize import like_escape

logger = logging.getLogger(__name__)


async def _providers_by_user(
    session: AsyncSession, user_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[ProviderRef]]:
    rows = await session.execute(
        select(UserProviderAssignment.user_id, Provider, ProviderGroup)
        .join(Provider, Provider.id == UserProviderAssignment.provider_id)
        .join(ProviderGroup, ProviderGroup.id == Provider.provider_group_id)
        .where(UserProviderAssignment.user_id.in_(list(user_ids)))
        .order_by(ProviderGroup.name, Provider.display_name)
    )
    out: dict[uuid.UUID, list[ProviderRef]] = defaultdict(list)
    for user_id, provider, group in rows:
        out[user_id].append(
            ProviderRef(id=provider.id, name=provider.display_name, group_name=group.name)
        )
    return out


def _out(user: User, providers: list[ProviderRef]) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        providers=providers,
    )


async def list_users(
    session: AsyncSession,
    *,
    q: str | None,
    role: UserRole | None,
    is_active: bool | None,
    limit: int,
    cursor: str | None,
) -> UserPage:
    email_key = func.lower(User.email)
    query = select(User)
    if q:
        term = f"%{like_escape(q)}%"
        query = query.where(
            or_(User.email.ilike(term, escape="\\"), User.full_name.ilike(term, escape="\\"))
        )
    if role is not None:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if cursor:
        last_email, last_id = decode_cursor(cursor, 2)
        query = query.where(
            or_(
                email_key > last_email,
                and_(email_key == last_email, User.id > uuid.UUID(last_id)),
            )
        )
    users = list(await session.scalars(query.order_by(email_key, User.id).limit(limit + 1)))

    has_more = len(users) > limit
    users = users[:limit]
    providers = await _providers_by_user(session, [u.id for u in users])
    return UserPage(
        items=[_out(u, providers.get(u.id, [])) for u in users],
        next_cursor=(
            encode_cursor([users[-1].email.lower(), str(users[-1].id)]) if has_more else None
        ),
        has_more=has_more,
    )


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return _out(user, (await _providers_by_user(session, [user.id])).get(user.id, []))


async def _validate_providers(session: AsyncSession, provider_ids: Iterable[int]) -> set[int]:
    wanted = set(provider_ids)
    found = set(await session.scalars(select(Provider.id).where(Provider.id.in_(wanted))))
    if missing := sorted(wanted - found):
        raise AppError(422, "UNKNOWN_PROVIDER", "Unknown provider ids", {"provider_ids": missing})
    return wanted


async def create_user(session: AsyncSession, admin: User, body: UserCreate) -> UserOut:
    taken = await session.scalar(select(User.id).where(func.lower(User.email) == body.email))
    if taken:
        raise AppError(409, "EMAIL_TAKEN", "A user with this email already exists")
    provider_ids = await _validate_providers(session, body.provider_ids)

    user = User(
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        password_hash=hash_password(body.password),
    )
    session.add(user)
    await session.flush()
    session.add_all(
        UserProviderAssignment(user_id=user.id, provider_id=pid, assigned_by=admin.id)
        for pid in provider_ids
    )
    await session.commit()
    logger.info("admin=%s created user=%s role=%s", admin.id, user.id, user.role)
    return await get_user(session, user.id)


async def update_user(
    session: AsyncSession, admin: User, user_id: uuid.UUID, body: UserUpdate
) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    if user.id == admin.id and (
        body.is_active is False or (body.role is not None and body.role != UserRole.ADMIN)
    ):
        raise AppError(409, "SELF_LOCKOUT", "You cannot deactivate or demote your own account")

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    await session.commit()
    logger.info(
        "admin=%s updated user=%s fields=%s",
        admin.id,
        user.id,
        sorted(body.model_dump(exclude_none=True, exclude={"password"}))
        + (["password"] if body.password else []),
    )
    await session.refresh(user)
    return await get_user(session, user.id)


async def replace_assignments(
    session: AsyncSession, admin: User, user_id: uuid.UUID, provider_ids: list[int]
) -> list[ProviderRef]:
    if await session.get(User, user_id) is None:
        raise NotFoundError("User not found")
    wanted = await _validate_providers(session, provider_ids)
    current = set(
        await session.scalars(
            select(UserProviderAssignment.provider_id).where(
                UserProviderAssignment.user_id == user_id
            )
        )
    )
    removed, added = current - wanted, wanted - current
    if removed:
        await session.execute(
            delete(UserProviderAssignment).where(
                UserProviderAssignment.user_id == user_id,
                UserProviderAssignment.provider_id.in_(removed),
            )
        )
    session.add_all(
        UserProviderAssignment(user_id=user_id, provider_id=pid, assigned_by=admin.id)
        for pid in added
    )
    await session.commit()
    logger.info(
        "admin=%s changed assignments user=%s added=%s removed=%s",
        admin.id,
        user_id,
        sorted(added),
        sorted(removed),
    )
    return (await _providers_by_user(session, [user_id])).get(user_id, [])


async def all_providers(session: AsyncSession) -> list[ProviderRef]:
    rows = await session.execute(
        select(Provider, ProviderGroup)
        .join(ProviderGroup, ProviderGroup.id == Provider.provider_group_id)
        .order_by(ProviderGroup.name, Provider.display_name)
    )
    return [ProviderRef(id=p.id, name=p.display_name, group_name=g.name) for p, g in rows]
