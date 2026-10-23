"""Idempotent demo seed: `python -m app.seed`.

Creates demo accounts only. Providers, payers, and members come from imported CSV
files. Accounts are inserted when missing, so re-running on every boot never
overwrites a password or an Admin's later assignment changes.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.core.security import hash_password
from app.models import User, UserRole

logger = logging.getLogger("app.seed")

DEMO_USERS: list[dict] = [
    {"email": "admin@salud.test", "full_name": "Avery Admin", "role": UserRole.ADMIN},
    {"email": "coder.one@salud.test", "full_name": "Casey Coder", "role": UserRole.CODER},
    {"email": "coder.two@salud.test", "full_name": "Jordan Coder", "role": UserRole.CODER},
]


async def seed_users(session: AsyncSession, password: str) -> int:
    created = 0
    for spec in DEMO_USERS:
        exists = await session.scalar(select(User.id).where(User.email == spec["email"]))
        if exists:
            continue
        session.add(
            User(
                email=spec["email"],
                full_name=spec["full_name"],
                role=spec["role"],
                password_hash=hash_password(password),
            )
        )
        created += 1
    return created


async def run_seed() -> None:
    async with SessionLocal() as session, session.begin():
        created = await seed_users(session, get_settings().seed_demo_password)
    logger.info("Seed complete: %d new users", created)


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        await run_seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
