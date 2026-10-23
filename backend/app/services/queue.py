"""Provider-scoped work queue: members with matching opportunities, and their drill-down.

Every query is restricted to the caller's provider assignments as stored at request time.
Records outside that scope are reported as 404, so their existence never leaks.
"""

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import ColumnElement, distinct, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.pagination import decode_cursor, encode_cursor
from app.models import (
    Disposition,
    Member,
    MemberPolicy,
    Opportunity,
    Payer,
    Provider,
    ProviderGroup,
    SourceRecord,
    User,
)
from app.models.enums import ACTIVE_DISPOSITIONS
from app.schemas.auth import ProviderRef
from app.schemas.queue import (
    HccCandidate,
    MemberDetail,
    MemberPage,
    MemberPolicyOut,
    MemberRef,
    OpportunityDetail,
    OpportunitySummary,
    PayerRef,
    QueueMember,
    SourceEvidence,
)
from app.services import access
from app.services.normalize import like_escape

_IS_ACTIVE = Opportunity.current_disposition.in_(ACTIVE_DISPOSITIONS)


@dataclass(frozen=True)
class OpportunityFilters:
    provider_id: int | None = None
    payer_id: int | None = None
    initiative: str | None = None
    dispositions: tuple[Disposition, ...] = ()
    performance_year: int | None = None


@dataclass(frozen=True)
class _SourceStats:
    initiatives: list[str]
    source_files: list[str]
    count: int
    last_dos: date | None


_NO_SOURCES = _SourceStats([], [], 0, None)


async def _scope(session: AsyncSession, user: User, provider_id: int | None) -> set[int]:
    allowed = await access.visible_provider_ids(session, user)
    if provider_id is None:
        return allowed
    if provider_id not in allowed:
        raise ForbiddenError("You are not assigned to this provider")
    return {provider_id}


def _conditions(filters: OpportunityFilters, providers: set[int]) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = [Opportunity.provider_id.in_(providers)]
    if filters.payer_id is not None:
        conds.append(Opportunity.payer_id == filters.payer_id)
    if filters.performance_year is not None:
        conds.append(Opportunity.performance_year == filters.performance_year)
    if filters.dispositions:
        conds.append(Opportunity.current_disposition.in_(filters.dispositions))
    if filters.initiative:
        # EXISTS rather than a join: an opportunity with several matching evidence rows
        # must still count once.
        conds.append(
            exists().where(
                SourceRecord.opportunity_id == Opportunity.id,
                SourceRecord.initiative == filters.initiative,
            )
        )
    return conds


def _query_context(filters: OpportunityFilters, q: str | None) -> str:
    payload = json.dumps({**asdict(filters), "q": q}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


async def list_members(
    session: AsyncSession,
    user: User,
    filters: OpportunityFilters,
    *,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> MemberPage:
    providers = await _scope(session, user, filters.provider_id)
    conds = _conditions(filters, providers)
    context = _query_context(filters, q)

    # Walk members in key order and probe for a matching opportunity, so a page costs
    # roughly `limit` index lookups regardless of how deep the cursor is.
    query = select(Member).where(exists().where(Opportunity.member_id == Member.id, *conds))
    if q:
        term = like_escape(q)
        query = query.where(
            or_(
                Member.external_member_id.ilike(f"{term}%", escape="\\"),
                Member.member_name.ilike(f"%{term}%", escape="\\"),
            )
        )
    if cursor:
        last_external_id, cursor_context = decode_cursor(cursor, 2)
        if cursor_context != context:
            raise AppError(400, "INVALID_CURSOR", "Pagination cursor does not match the filters")
        query = query.where(Member.external_member_id > last_external_id)
    members = list(
        await session.scalars(query.order_by(Member.external_member_id).limit(limit + 1))
    )

    has_more = len(members) > limit
    members = members[:limit]
    stats = await session.execute(
        select(
            Opportunity.member_id,
            func.count(),
            func.count().filter(_IS_ACTIVE),
            func.array_agg(distinct(Provider.display_name)),
            func.array_agg(distinct(Payer.display_name)),
        )
        .join(Provider, Provider.id == Opportunity.provider_id)
        .join(Payer, Payer.id == Opportunity.payer_id)
        .where(Opportunity.member_id.in_([m.id for m in members]), *conds)
        .group_by(Opportunity.member_id)
    )
    by_member = {row[0]: row for row in stats}

    items = []
    for m in members:
        _, matched, active, provider_names, payer_names = by_member[m.id]
        items.append(
            QueueMember(
                member_id=m.id,
                external_member_id=m.external_member_id,
                member_name=m.member_name,
                date_of_birth=m.date_of_birth,
                matched_opportunity_count=matched,
                open_opportunity_count=active,
                providers=sorted(provider_names),
                payers=sorted(payer_names),
            )
        )
    next_cursor = encode_cursor([members[-1].external_member_id, context]) if has_more else None
    return MemberPage(items=items, next_cursor=next_cursor, has_more=has_more)


async def get_member(session: AsyncSession, user: User, member_id: uuid.UUID) -> MemberDetail:
    providers = await access.visible_provider_ids(session, user)
    scoped = (Opportunity.member_id == member_id, Opportunity.provider_id.in_(providers))

    member = await session.get(Member, member_id)
    total, active = (
        await session.execute(select(func.count(), func.count().filter(_IS_ACTIVE)).where(*scoped))
    ).one()
    if member is None or total == 0:
        raise NotFoundError("Member not found")

    provider_rows = await session.execute(
        select(Provider, ProviderGroup)
        .join(ProviderGroup, ProviderGroup.id == Provider.provider_group_id)
        .where(Provider.id.in_(select(Opportunity.provider_id).where(*scoped)))
        .order_by(ProviderGroup.name, Provider.display_name)
    )
    # Only policies with payers the caller can see opportunities for.
    policy_rows = await session.execute(
        select(Payer.display_name, MemberPolicy.policy_number)
        .join(Payer, Payer.id == MemberPolicy.payer_id)
        .where(
            MemberPolicy.member_id == member_id,
            MemberPolicy.payer_id.in_(select(Opportunity.payer_id).where(*scoped)),
        )
        .order_by(Payer.display_name, MemberPolicy.policy_number)
    )
    return MemberDetail(
        id=member.id,
        external_member_id=member.external_member_id,
        member_name=member.member_name,
        date_of_birth=member.date_of_birth,
        policies=[MemberPolicyOut(payer_name=p, policy_number=n) for p, n in policy_rows],
        providers=[
            ProviderRef(id=p.id, name=p.display_name, group_name=g.name) for p, g in provider_rows
        ],
        total_opportunity_count=total,
        open_opportunity_count=active,
    )


def _opportunity_query():
    return (
        select(Opportunity, Payer, Provider, ProviderGroup)
        .join(Payer, Payer.id == Opportunity.payer_id)
        .join(Provider, Provider.id == Opportunity.provider_id)
        .join(ProviderGroup, ProviderGroup.id == Provider.provider_group_id)
    )


async def _source_stats(
    session: AsyncSession, opportunity_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, _SourceStats]:
    rows = await session.execute(
        select(
            SourceRecord.opportunity_id,
            func.array_agg(distinct(SourceRecord.initiative)),
            func.array_agg(distinct(SourceRecord.source_file)),
            func.count(),
            func.max(SourceRecord.last_dos),
        )
        .where(SourceRecord.opportunity_id.in_(opportunity_ids))
        .group_by(SourceRecord.opportunity_id)
    )
    return {
        opp_id: _SourceStats(sorted(initiatives), sorted(files), count, last_dos)
        for opp_id, initiatives, files, count, last_dos in rows
    }


def _summary_fields(
    opp: Opportunity, payer: Payer, provider: Provider, group: ProviderGroup, stats: _SourceStats
) -> dict:
    return {
        "id": opp.id,
        "performance_year": opp.performance_year,
        "icd10_code": opp.icd10_code,
        "icd10_description": opp.icd10_description,
        "hcc_code": opp.hcc_code,
        "hcc_description": opp.hcc_description,
        "hcc_conflict": opp.hcc_conflict,
        "payer": PayerRef(id=payer.id, name=payer.display_name),
        "provider": ProviderRef(id=provider.id, name=provider.display_name, group_name=group.name),
        "current_disposition": opp.current_disposition,
        "disposition_version": opp.disposition_version,
        "last_disposition_at": opp.last_disposition_at,
        "initiatives": stats.initiatives,
        "source_files": stats.source_files,
        "source_count": stats.count,
        "last_dos": stats.last_dos,
    }


async def list_member_opportunities(
    session: AsyncSession, user: User, member_id: uuid.UUID, filters: OpportunityFilters
) -> list[OpportunitySummary]:
    allowed = await access.visible_provider_ids(session, user)
    visible = await session.scalar(
        select(
            exists().where(Opportunity.member_id == member_id, Opportunity.provider_id.in_(allowed))
        )
    )
    if not visible:
        raise NotFoundError("Member not found")

    providers = await _scope(session, user, filters.provider_id)
    rows = (
        await session.execute(
            _opportunity_query()
            .where(Opportunity.member_id == member_id, *_conditions(filters, providers))
            .order_by(
                Opportunity.performance_year.desc(), Opportunity.icd10_code, Payer.display_name
            )
        )
    ).all()
    stats = await _source_stats(session, [row[0].id for row in rows])
    return [
        OpportunitySummary(**_summary_fields(*row, stats.get(row[0].id, _NO_SOURCES)))
        for row in rows
    ]


async def get_opportunity(
    session: AsyncSession, user: User, opportunity_id: uuid.UUID
) -> OpportunityDetail:
    allowed = await access.visible_provider_ids(session, user)
    row = (
        await session.execute(
            _opportunity_query()
            .add_columns(Member)
            .join(Member, Member.id == Opportunity.member_id)
            .where(Opportunity.id == opportunity_id, Opportunity.provider_id.in_(allowed))
        )
    ).first()
    if row is None:
        raise NotFoundError("Opportunity not found")
    opp, payer, provider, group, member = row

    sources = list(
        await session.scalars(
            select(SourceRecord)
            .where(SourceRecord.opportunity_id == opp.id)
            .order_by(SourceRecord.last_dos.desc().nulls_last(), SourceRecord.id)
        )
    )
    stats = (await _source_stats(session, [opp.id])).get(opp.id, _NO_SOURCES)

    candidates: list[HccCandidate] = []
    if opp.hcc_conflict:
        sibling_rows = await session.execute(
            select(Opportunity, Payer.display_name)
            .join(Payer, Payer.id == Opportunity.payer_id)
            .where(
                Opportunity.member_id == opp.member_id,
                Opportunity.performance_year == opp.performance_year,
                Opportunity.icd10_code == opp.icd10_code,
                Opportunity.id != opp.id,
                Opportunity.provider_id.in_(allowed),
            )
            .order_by(Payer.display_name)
        )
        candidates = [
            HccCandidate(
                opportunity_id=sibling.id,
                payer_name=payer_name,
                hcc_code=sibling.hcc_code,
                hcc_description=sibling.hcc_description,
            )
            for sibling, payer_name in sibling_rows
        ]

    changed_by = (
        await session.scalar(select(User.email).where(User.id == opp.last_disposition_by))
        if opp.last_disposition_by
        else None
    )
    return OpportunityDetail(
        **_summary_fields(opp, payer, provider, group, stats),
        member=MemberRef(
            id=member.id,
            external_member_id=member.external_member_id,
            member_name=member.member_name,
            date_of_birth=member.date_of_birth,
        ),
        current_note=opp.current_note,
        last_disposition_by_email=changed_by,
        sources=[
            SourceEvidence(
                id=s.id,
                source_file=s.source_file,
                source_row_number=s.source_row_number,
                policy_number=s.policy_number,
                initiative=s.initiative,
                evidence=s.evidence,
                last_dos=s.last_dos,
                reported_hcc_code=s.reported_hcc_code,
                reported_hcc_description=s.reported_hcc_description,
                imported_at=s.created_at,
            )
            for s in sources
        ],
        hcc_candidates=candidates,
    )


async def initiatives(session: AsyncSession, user: User) -> list[str]:
    allowed = await access.visible_provider_ids(session, user)
    rows = await session.scalars(
        select(SourceRecord.initiative)
        .distinct()
        .join(Opportunity, Opportunity.id == SourceRecord.opportunity_id)
        .where(Opportunity.provider_id.in_(allowed))
        .order_by(SourceRecord.initiative)
    )
    return list(rows)


async def performance_years(session: AsyncSession, user: User) -> list[int]:
    allowed = await access.visible_provider_ids(session, user)
    rows = await session.scalars(
        select(Opportunity.performance_year)
        .distinct()
        .where(Opportunity.provider_id.in_(allowed))
        .order_by(Opportunity.performance_year.desc())
    )
    return list(rows)


async def payers(session: AsyncSession) -> list[PayerRef]:
    rows = await session.scalars(select(Payer).order_by(Payer.display_name))
    return [PayerRef(id=p.id, name=p.display_name) for p in rows]
