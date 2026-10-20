import os
from collections.abc import AsyncIterator, Awaitable, Callable

from app.core.config import Settings

# Point the app at a dedicated test database before any engine is created.
os.environ["DATABASE_URL"] = (
    os.environ.get("TEST_DATABASE_URL")
    or Settings().database_url.rsplit("/", 1)[0] + "/salud_mra_test"
)

import httpx2  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.middleware import CSRF_HEADER  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base, User, UserProviderAssignment, UserRole  # noqa: E402
from app.seed import seed_providers  # noqa: E402

TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def client() -> AsyncIterator[httpx2.AsyncClient]:
    transport = httpx2.ASGITransport(app=create_app())
    async with httpx2.AsyncClient(
        transport=transport, base_url="http://test", headers={CSRF_HEADER: "fetch"}
    ) as c:
        yield c


@pytest.fixture
async def provider_ids() -> dict[str, int]:
    async with SessionLocal() as session, session.begin():
        return await seed_providers(session)


MakeUser = Callable[..., Awaitable[User]]


@pytest.fixture
def make_user(provider_ids: dict[str, int]) -> MakeUser:
    async def _make(
        email: str,
        role: UserRole = UserRole.CODER,
        providers: tuple[str, ...] = (),
        is_active: bool = True,
    ) -> User:
        async with SessionLocal() as session, session.begin():
            user = User(
                email=email,
                full_name=email.split("@")[0],
                role=role,
                is_active=is_active,
                password_hash=hash_password(TEST_PASSWORD),
            )
            session.add(user)
            await session.flush()
            for name in providers:
                session.add(UserProviderAssignment(user_id=user.id, provider_id=provider_ids[name]))
        return user

    return _make


async def login(client: httpx2.AsyncClient, email: str, password: str = TEST_PASSWORD):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})
