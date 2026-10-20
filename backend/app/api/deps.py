from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.errors import ForbiddenError, UnauthenticatedError
from app.core.security import decode_access_token
from app.models import User, UserRole

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(request: Request, session: SessionDep) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        raise UnauthenticatedError()
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthenticatedError()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError()
    return user


async def require_coder(user: CurrentUser) -> User:
    if user.role != UserRole.CODER:
        raise ForbiddenError("Only coders can set dispositions")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
CoderUser = Annotated[User, Depends(require_coder)]
