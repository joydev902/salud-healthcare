from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthenticatedError
from app.core.security import verify_password
from app.models import User


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    """Same error for unknown email, wrong password and deactivated account."""
    user = await session.scalar(select(User).where(func.lower(User.email) == email.lower()))
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok or not user.is_active:
        raise UnauthenticatedError("Invalid email or password")
    return user
