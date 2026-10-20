from fastapi import APIRouter, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import CurrentUserOut, LoginRequest, ProviderRef
from app.services import access
from app.services.auth import authenticate

router = APIRouter(prefix="/auth", tags=["auth"])


async def _current_user_out(session: AsyncSession, user: User) -> CurrentUserOut:
    providers = await access.assigned_providers(session, user.id)
    return CurrentUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        providers=[
            ProviderRef(id=p.id, name=p.display_name, group_name=g.name) for p, g in providers
        ],
    )


@router.post("/login", response_model=CurrentUserOut)
async def login(body: LoginRequest, response: Response, session: SessionDep) -> CurrentUserOut:
    user = await authenticate(session, body.email, body.password)
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_access_token(user.id),
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/api",
    )
    return await _current_user_out(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(get_settings().session_cookie_name, path="/api")


@router.get("/me", response_model=CurrentUserOut)
async def me(user: CurrentUser, session: SessionDep) -> CurrentUserOut:
    return await _current_user_out(session, user)
