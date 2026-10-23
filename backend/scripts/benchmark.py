"""Load the synthetic dataset into a separate database and benchmark the work queue.

    python run.py bench                 # from the repo root
    BENCH_ROWS=500000 python run.py bench

Uses `salud_mra_bench` (or BENCH_DATABASE_URL) so the dev and test databases are untouched.
Data is imported through the real ingestion service; timings exercise the real queue
service end to end (SQL + Python), and EXPLAIN plans are captured from the exact SQL it
emits. Results are written to docs/performance.md.
"""

import asyncio
import os
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.core.config import REPO_ROOT, Settings

BENCH_URL = (
    os.environ.get("BENCH_DATABASE_URL")
    or Settings().database_url.rsplit("/", 1)[0] + "/salud_mra_bench"
)
os.environ["DATABASE_URL"] = BENCH_URL

from sqlalchemy import delete, event, func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Disposition,
    Member,
    Opportunity,
    Provider,
    ProviderGroup,
    SourceRecord,
    User,
    UserProviderAssignment,
    UserRole,
)
from app.services import ingestion, queue  # noqa: E402
from app.services.queue import OpportunityFilters  # noqa: E402
from scripts.synthetic import generate  # noqa: E402

ROWS = int(os.environ.get("BENCH_ROWS", "200000"))
MEMBERS = max(1000, ROWS // 8)
RUNS, WARMUP = 15, 3
REPORT = REPO_ROOT / "docs" / "performance.md"
ACTIVE = tuple(
    sorted({Disposition.OPEN, Disposition.PENDING_CHART, Disposition.REFERRED_TO_PROVIDER})
)


async def ensure_database() -> None:
    base, name = BENCH_URL.rsplit("/", 1)
    admin_engine = create_async_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
    await admin_engine.dispose()


def migrate() -> None:
    subprocess.check_call(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DATABASE_URL": BENCH_URL},
    )


async def ensure_user(session: AsyncSession, email: str, role: UserRole) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            full_name=email.split("@")[0],
            role=role,
            password_hash=hash_password("bench-password-123"),
        )
        session.add(user)
        await session.flush()
    return user


async def load_data() -> tuple[User, User]:
    async with SessionLocal() as session:
        admin = await ensure_user(session, "bench.admin@salud.test", UserRole.ADMIN)
        coder = await ensure_user(session, "bench.coder@salud.test", UserRole.CODER)
        await session.commit()
        existing = await session.scalar(select(func.count()).select_from(SourceRecord))

    if existing < ROWS:
        print(f"Generating {ROWS:,} synthetic rows for {MEMBERS:,} members...", flush=True)
        files = generate(rows=ROWS, members=MEMBERS)
        for i, (filename, content) in enumerate(files.items(), 1):
            async with SessionLocal() as session:
                batch = await ingestion.import_csv(
                    session, filename=filename, content=content, uploaded_by=admin.id
                )
            print(
                f"  [{i}/{len(files)}] {filename}: {batch.total_rows:,} rows, {batch.status}",
                flush=True,
            )
        await seed_dispositions(coder)

    async with SessionLocal() as session:
        # Admin sees everything; the coder is scoped to one provider group (5 providers).
        all_ids = list(await session.scalars(select(Provider.id)))
        group_ids = list(
            await session.scalars(
                select(Provider.id)
                .join(ProviderGroup, ProviderGroup.id == Provider.provider_group_id)
                .where(ProviderGroup.name == "Palm Medical Group")
            )
        )
        for user, ids in ((admin, all_ids), (coder, group_ids)):
            await session.execute(
                delete(UserProviderAssignment).where(UserProviderAssignment.user_id == user.id)
            )
            session.add_all(UserProviderAssignment(user_id=user.id, provider_id=p) for p in ids)
        await session.commit()
    async with engine.begin() as conn:
        await conn.execute(text("ANALYZE"))
    return admin, coder


async def seed_dispositions(coder: User) -> None:
    """Decide ~35% of opportunities (with matching history) so status filters are realistic."""
    async with SessionLocal() as session:
        await session.execute(
            text(
                """
                WITH picked AS (
                    SELECT id, (ARRAY['CONFIRMED','DENIED','PENDING_CHART','REFERRED_TO_PROVIDER'])
                               [1 + floor(random() * 4)::int] AS status
                    FROM opportunities WHERE current_disposition = 'OPEN' AND random() < 0.35
                ), updated AS (
                    UPDATE opportunities o
                    SET current_disposition = p.status,
                        current_note = 'Synthetic benchmark decision',
                        disposition_version = o.disposition_version + 1,
                        last_disposition_at = now(), last_disposition_by = :uid
                    FROM picked p WHERE o.id = p.id
                    RETURNING o.id, p.status, o.disposition_version
                )
                INSERT INTO disposition_history
                    (opportunity_id, changed_by, changed_at, old_status, new_status, note,
                     old_version, new_version)
                SELECT id, :uid, now(), 'OPEN', status, 'Synthetic benchmark decision',
                       disposition_version - 1, disposition_version
                FROM updated
                """
            ),
            {"uid": coder.id},
        )
        await session.commit()


class SqlCapture:
    """Records the statements the service emits so they can be EXPLAINed verbatim."""

    def __init__(self) -> None:
        self.active = False
        self.statements: list[tuple[str, object]] = []
        event.listen(engine.sync_engine, "before_cursor_execute", self._record)

    def _record(self, _conn, _cursor, statement, parameters, _context, _executemany) -> None:
        if self.active:
            self.statements.append((statement, parameters))


async def timed(fn: Callable[[AsyncSession], Awaitable[object]]) -> tuple[float, float]:
    samples = []
    for i in range(WARMUP + RUNS):
        async with SessionLocal() as session:
            started = time.perf_counter()
            await fn(session)
            if i >= WARMUP:
                samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    return statistics.median(samples), samples[int(len(samples) * 0.95) - 1]


async def explain(
    capture: SqlCapture, fn: Callable[[AsyncSession], Awaitable[object]], marker: str
) -> str:
    capture.statements.clear()
    capture.active = True
    async with SessionLocal() as session:
        await fn(session)
    capture.active = False
    statement, params = next((s, p) for s, p in capture.statements if marker in s)
    async with engine.connect() as conn:
        result = await conn.exec_driver_sql(f"EXPLAIN (ANALYZE, BUFFERS) {statement}", params)
        return "\n".join(row[0] for row in result)


async def cursor_after(user: User, pages: int) -> str:
    cursor = None
    async with SessionLocal() as session:
        for _ in range(pages):
            page = await queue.list_members(
                session, user, OpportunityFilters(), q=None, limit=25, cursor=cursor
            )
            cursor = page.next_cursor
    assert cursor, "dataset too small for the deep-page scenario"
    return cursor


async def main() -> None:
    admin, coder = await load_data()
    capture = SqlCapture()

    async with SessionLocal() as session:
        counts = {
            "members": await session.scalar(select(func.count()).select_from(Member)),
            "opportunities": await session.scalar(select(func.count()).select_from(Opportunity)),
            "source rows": await session.scalar(select(func.count()).select_from(SourceRecord)),
            "providers": await session.scalar(select(func.count()).select_from(Provider)),
        }
        pg_version = await session.scalar(text("SHOW server_version"))
        import_seconds = await session.scalar(
            text(
                "SELECT extract(epoch FROM sum(finished_at - started_at)) FROM upload_batches "
                "WHERE uploaded_by = :uid"
            ),
            {"uid": admin.id},
        )
        sample_member = await session.scalar(
            select(Opportunity.member_id)
            .join(
                UserProviderAssignment,
                UserProviderAssignment.provider_id == Opportunity.provider_id,
            )
            .where(UserProviderAssignment.user_id == coder.id)
            .limit(1)
        )
        sample_opp = await session.scalar(
            select(Opportunity.id).where(Opportunity.member_id == sample_member).limit(1)
        )
        payer_id = await session.scalar(text("SELECT id FROM payers ORDER BY display_name LIMIT 1"))

    deep_cursor = await cursor_after(admin, 200)

    def members(user: User, filters: OpportunityFilters | None = None, q=None, cursor=None):
        filters = filters or OpportunityFilters()
        return lambda s: queue.list_members(s, user, filters, q=q, limit=25, cursor=cursor)

    scenarios = [
        ("Coder queue, first page (no filters)", members(coder)),
        (
            "Coder queue, active dispositions",
            members(coder, OpportunityFilters(dispositions=ACTIVE)),
        ),
        ("Coder queue, initiative = Audit", members(coder, OpportunityFilters(initiative="Audit"))),
        (
            "Coder queue, payer + PY2025 + CONFIRMED",
            members(
                coder,
                OpportunityFilters(
                    payer_id=payer_id, performance_year=2025, dispositions=(Disposition.CONFIRMED,)
                ),
            ),
        ),
        ("Coder queue, member search 'SYN0012'", members(coder, q="SYN0012")),
        ("Admin queue, first page (all providers)", members(admin)),
        ("Admin queue, page 201 via cursor", members(admin, cursor=deep_cursor)),
        (
            "Admin queue, Screenings + DENIED",
            members(
                admin,
                OpportunityFilters(initiative="Screenings", dispositions=(Disposition.DENIED,)),
            ),
        ),
        ("Member detail", lambda s: queue.get_member(s, coder, sample_member)),
        (
            "Member opportunities",
            lambda s: queue.list_member_opportunities(
                s, coder, sample_member, OpportunityFilters()
            ),
        ),
        ("Opportunity detail + evidence", lambda s: queue.get_opportunity(s, coder, sample_opp)),
    ]
    results = []
    for name, fn in scenarios:
        median, p95 = await timed(fn)
        results.append((name, median, p95))
        print(f"{name:<45} median {median:7.1f} ms   p95 {p95:7.1f} ms", flush=True)

    plans = [
        (
            "Coder queue, active dispositions — member page query",
            await explain(
                capture, members(coder, OpportunityFilters(dispositions=ACTIVE)), "FROM members"
            ),
        ),
        (
            "Coder queue — per-page counts query",
            await explain(capture, members(coder), "array_agg"),
        ),
        (
            "Admin queue, page 201 via cursor — member page query",
            await explain(capture, members(admin, cursor=deep_cursor), "FROM members"),
        ),
        (
            "Admin queue, Screenings + DENIED — member page query",
            await explain(
                capture,
                members(
                    admin,
                    OpportunityFilters(initiative="Screenings", dispositions=(Disposition.DENIED,)),
                ),
                "FROM members",
            ),
        ),
    ]
    write_report(counts, pg_version, import_seconds, results, plans)
    await engine.dispose()


def write_report(counts, pg_version, import_seconds, results, plans) -> None:
    lines = [
        "# Work queue performance",
        "",
        "Generated by `python run.py bench` (`backend/scripts/benchmark.py`). Synthetic data only.",
        "",
        "## Dataset",
        "",
        "| | |",
        "|---|---|",
        *(f"| {k} | {v:,} |" for k, v in counts.items()),
        f"| PostgreSQL | {pg_version} |",
        f"| Host | {platform.system()} {platform.release()}, Python {platform.python_version()} |",
    ]
    if import_seconds:
        import_seconds = float(import_seconds)
        rate = counts["source rows"] / import_seconds
        lines.append(
            f"| Import time | {import_seconds:.1f} s across all uploads "
            f"({rate:,.0f} rows/s through the ingestion service) |"
        )
    lines += [
        "",
        "The coder is assigned one provider group (5 of 40 providers, ~12% of the data); the",
        "admin is assigned all providers. ~35% of opportunities carry a decision.",
        "",
        "## Timings",
        "",
        f"Service-level latency (SQL + Python), {RUNS} runs after {WARMUP} warm-up runs, "
        "page size 25.",
        "",
        "| Scenario | Median (ms) | p95 (ms) |",
        "|---|---:|---:|",
        *(f"| {name} | {median:.1f} | {p95:.1f} |" for name, median, p95 in results),
        "",
        "## Query plans",
        "",
    ]
    for title, plan in plans:
        lines += [f"### {title}", "", "```text", plan, "```", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {REPORT}")


if __name__ == "__main__":
    asyncio.run(ensure_database())
    migrate()
    asyncio.run(main())
