"""Canonical opportunity rules that depend on all linked evidence."""

import uuid
from collections import defaultdict

from sqlalchemy import select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Opportunity, SourceRecord

ConditionKey = tuple[uuid.UUID, int, str]  # (member_id, performance_year, icd10_code)


async def reconcile_hcc(session: AsyncSession, keys: set[ConditionKey]) -> None:
    """Recompute HCC agreement for each member/year/ICD-10 condition.

    An opportunity shows a canonical HCC only when its own sources agree on one code.
    `hcc_conflict` is raised when any source for the same member, year and diagnosis --
    across payers -- reports a different HCC. Reported values stay on source_records.
    """
    if not keys:
        return
    cols = (Opportunity.member_id, Opportunity.performance_year, Opportunity.icd10_code)
    key_list = list(keys)
    rows = []
    for start in range(0, len(key_list), 1000):
        chunk = key_list[start : start + 1000]
        result = await session.execute(
            select(
                Opportunity.id,
                *cols,
                SourceRecord.reported_hcc_code,
                SourceRecord.reported_hcc_description,
            )
            .join(SourceRecord, SourceRecord.opportunity_id == Opportunity.id)
            .where(tuple_(*cols).in_(chunk))
        )
        rows.extend(result.all())

    own: dict[uuid.UUID, dict[str, str | None]] = {}
    by_condition: dict[ConditionKey, set[str]] = defaultdict(set)
    condition_of: dict[uuid.UUID, ConditionKey] = {}
    for opp_id, member_id, year, icd, hcc, hcc_desc in rows:
        condition_of[opp_id] = (member_id, year, icd)
        codes = own.setdefault(opp_id, {})
        if hcc:
            by_condition[(member_id, year, icd)].add(hcc)
            codes.setdefault(hcc, hcc_desc)

    params = []
    for opp_id, condition in condition_of.items():
        codes = own[opp_id]
        hcc_code, hcc_desc = next(iter(codes.items())) if len(codes) == 1 else (None, None)
        params.append(
            {
                "id": opp_id,
                "hcc_code": hcc_code,
                "hcc_description": hcc_desc,
                "hcc_conflict": len(by_condition[condition]) > 1,
            }
        )
    if params:
        await session.execute(update(Opportunity), params)
