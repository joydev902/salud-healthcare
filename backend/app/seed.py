"""Idempotent demo seed: `python -m app.seed`.

Creates the provider directory found in the sample CSV and demo accounts. Accounts and
their initial provider assignments are only created when missing, so re-running on every
boot never overwrites passwords or undoes an Admin's assignment changes.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.core.security import hash_password
from app.models import Provider, ProviderGroup, User, UserProviderAssignment, UserRole
from app.services.normalize import normalize_name

logger = logging.getLogger("app.seed")

PROVIDER_DIRECTORY: dict[str, list[str]] = {
    "Palm Medical Group": ["Dr. Garcia", "Dr. Thompson"],
    "Sunshine Health Center": ["Dr. Patel"],
    "Coastal Primary Care": ["Dr. Nguyen"],
}

DEMO_USERS: list[dict] = [
    {
        "email": "admin@salud.test",
        "full_name": "Avery Admin",
        "role": UserRole.ADMIN,
        "providers": ["Dr. Garcia", "Dr. Thompson", "Dr. Patel", "Dr. Nguyen"],
    },
    {
        "email": "coder.one@salud.test",
        "full_name": "Casey Coder",
        "role": UserRole.CODER,
        "providers": ["Dr. Garcia", "Dr. Thompson"],
    },
    {
        "email": "coder.two@salud.test",
        "full_name": "Jordan Coder",
        "role": UserRole.CODER,
        "providers": ["Dr. Patel", "Dr. Nguyen"],
    },
]


async def seed_providers(session: AsyncSession) -> dict[str, int]:
    for group_name, provider_names in PROVIDER_DIRECTORY.items():
        await session.execute(
            insert(ProviderGroup)
            .values(name=group_name, normalized_name=normalize_name(group_name))
            .on_conflict_do_nothing(index_elements=["normalized_name"])
        )
        group_id = await session.scalar(
            select(ProviderGroup.id).where(
                ProviderGroup.normalized_name == normalize_name(group_name)
            )
        )
        for name in provider_names:
            await session.execute(
                insert(Provider)
                .values(
                    provider_group_id=group_id,
                    display_name=name,
                    normalized_name=normalize_name(name),
                )
                .on_conflict_do_nothing(index_elements=["provider_group_id", "normalized_name"])
            )

    rows = await session.execute(select(Provider.normalized_name, Provider.id))
    return {name: provider_id for name, provider_id in rows}


async def seed_users(session: AsyncSession, provider_ids: dict[str, int], password: str) -> int:
    created = 0
    for spec in DEMO_USERS:
        exists = await session.scalar(select(User.id).where(User.email == spec["email"]))
        if exists:
            continue
        user = User(
            email=spec["email"],
            full_name=spec["full_name"],
            role=spec["role"],
            password_hash=hash_password(password),
        )
        session.add(user)
        await session.flush()
        session.add_all(
            UserProviderAssignment(user_id=user.id, provider_id=provider_ids[normalize_name(name)])
            for name in spec["providers"]
        )
        created += 1
    return created


async def run_seed() -> None:
    async with SessionLocal() as session, session.begin():
        provider_ids = await seed_providers(session)
        created = await seed_users(session, provider_ids, get_settings().seed_demo_password)
    logger.info("Seed complete: %d providers, %d new users", len(provider_ids), created)


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        await run_seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
