"""CSV import pipeline: batch log -> parse/validate -> resolve identities -> dedupe -> persist.

Database work is set-based (bulk upserts keyed by natural keys) so cost scales with the
number of distinct entities, not with one round trip per CSV row.
"""

import hashlib
import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import (
    Member,
    MemberPolicy,
    Opportunity,
    Payer,
    Provider,
    ProviderGroup,
    SourceRecord,
    UploadBatch,
    UploadStatus,
)
from app.services.csv_parser import (
    HeaderError,
    ParsedRow,
    RowIssue,
    decode_csv_bytes,
    parse_csv,
)
from app.services.normalize import normalize_name
from app.services.opportunity import reconcile_hcc

logger = logging.getLogger(__name__)

MAX_REPORTED_ISSUES = 200
_CHUNK = 1000


@dataclass
class _Context:
    payer_ids: dict[str, int]
    provider_ids: dict[tuple[str, str], int]
    member_ids: dict[str, uuid.UUID]


def _chunks(items: Sequence[Any], size: int = _CHUNK) -> Iterable[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _issues_json(issues: list[RowIssue]) -> list[dict[str, Any]]:
    return [
        {"row": i.row, "field": i.field, "reason": i.reason} for i in issues[:MAX_REPORTED_ISSUES]
    ]


async def import_csv(
    session: AsyncSession, *, filename: str, content: bytes, uploaded_by: uuid.UUID
) -> UploadBatch:
    batch = UploadBatch(
        uploaded_filename=filename[:255],
        sha256=hashlib.sha256(content).hexdigest(),
        uploaded_by=uploaded_by,
        status=UploadStatus.PROCESSING,
    )
    session.add(batch)
    await session.commit()  # the attempt is recorded even if processing fails

    try:
        text = decode_csv_bytes(content)
        parsed = parse_csv(text)
    except UnicodeDecodeError:
        await _fail(session, batch, "File is not valid UTF-8 text", {"reason": "encoding"})
        raise AppError(
            400, "INVALID_FILE", "File is not valid UTF-8 CSV", {"upload_id": str(batch.id)}
        ) from None
    except HeaderError as exc:
        await _fail(session, batch, str(exc), {"missing_columns": exc.missing})
        raise AppError(
            422,
            "MISSING_COLUMNS",
            "Required CSV columns are missing",
            {"missing_columns": exc.missing, "upload_id": str(batch.id)},
        ) from None

    try:
        errors = list(parsed.errors)
        warnings = list(parsed.warnings)
        if parsed.extra_columns:
            warnings.insert(
                0, RowIssue(1, None, f"Ignored extra columns: {', '.join(parsed.extra_columns)}")
            )

        ctx = await _resolve_reference_data(session, parsed.rows)
        rows, policy_errors = await _resolve_members_and_policies(session, parsed.rows, ctx)
        errors.extend(policy_errors)
        member_warnings = await _member_consistency_warnings(session, rows, ctx)
        warnings.extend(member_warnings)

        new_opportunities, opp_ids = await _upsert_opportunities(session, rows, ctx)
        inserted = await _insert_source_records(session, rows, ctx, opp_ids, batch.id)
        await reconcile_hcc(
            session,
            {(ctx.member_ids[r.member_id], r.performance_year, r.icd10_code) for r in rows},
        )

        errors.sort(key=lambda i: i.row)
        rejected = len({e.row for e in errors})
        if rows:
            status = UploadStatus.COMPLETED_WITH_ERRORS if rejected else UploadStatus.COMPLETED
        else:
            status = UploadStatus.FAILED

        batch.status = status
        batch.total_rows = parsed.total_rows
        batch.inserted_rows = inserted
        batch.duplicate_rows = len(rows) - inserted
        batch.rejected_rows = rejected
        batch.new_opportunities = new_opportunities
        batch.finished_at = datetime.now(UTC)
        batch.error_summary = {
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": _issues_json(errors),
            "warnings": _issues_json(warnings),
        }
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("Import failed upload_id=%s", batch.id)
        await _fail(session, batch, "Unexpected error while importing", {"reason": "internal"})
        raise

    return batch


async def _fail(
    session: AsyncSession, batch: UploadBatch, message: str, details: dict[str, Any]
) -> None:
    await session.execute(
        update(UploadBatch)
        .where(UploadBatch.id == batch.id)
        .values(
            status=UploadStatus.FAILED,
            finished_at=datetime.now(UTC),
            error_summary={"message": message, **details},
        )
    )
    await session.commit()
    await session.refresh(batch)


async def _resolve_reference_data(session: AsyncSession, rows: list[ParsedRow]) -> _Context:
    payers = {normalize_name(r.payer_name): r.payer_name for r in rows}
    if payers:
        await session.execute(
            insert(Payer)
            .values([{"display_name": v, "normalized_name": k} for k, v in payers.items()])
            .on_conflict_do_nothing(index_elements=["normalized_name"])
        )
    payer_ids = dict(
        (
            await session.execute(
                select(Payer.normalized_name, Payer.id).where(
                    Payer.normalized_name.in_(list(payers))
                )
            )
        ).all()
    )

    groups = {normalize_name(r.provider_group): r.provider_group for r in rows}
    if groups:
        await session.execute(
            insert(ProviderGroup)
            .values([{"name": v, "normalized_name": k} for k, v in groups.items()])
            .on_conflict_do_nothing(index_elements=["normalized_name"])
        )
    group_ids = dict(
        (
            await session.execute(
                select(ProviderGroup.normalized_name, ProviderGroup.id).where(
                    ProviderGroup.normalized_name.in_(list(groups))
                )
            )
        ).all()
    )

    providers = {
        (normalize_name(r.provider_group), normalize_name(r.provider_name)): r.provider_name
        for r in rows
    }
    if providers:
        await session.execute(
            insert(Provider)
            .values(
                [
                    {
                        "provider_group_id": group_ids[g],
                        "display_name": name,
                        "normalized_name": p,
                    }
                    for (g, p), name in providers.items()
                ]
            )
            .on_conflict_do_nothing(index_elements=["provider_group_id", "normalized_name"])
        )
    id_to_group = {v: k for k, v in group_ids.items()}
    provider_rows = await session.execute(
        select(Provider.provider_group_id, Provider.normalized_name, Provider.id).where(
            Provider.provider_group_id.in_(list(group_ids.values()))
        )
    )
    provider_ids = {(id_to_group[g], n): pid for g, n, pid in provider_rows}

    return _Context(payer_ids=payer_ids, provider_ids=provider_ids, member_ids={})


async def _resolve_members_and_policies(
    session: AsyncSession, rows: list[ParsedRow], ctx: _Context
) -> tuple[list[ParsedRow], list[RowIssue]]:
    first_by_member: dict[str, ParsedRow] = {}
    for r in rows:
        first_by_member.setdefault(r.member_id, r)
    for chunk in _chunks(list(first_by_member.values())):
        await session.execute(
            insert(Member)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "external_member_id": r.member_id,
                        "member_name": r.member_name,
                        "date_of_birth": r.date_of_birth,
                    }
                    for r in chunk
                ]
            )
            .on_conflict_do_nothing(index_elements=["external_member_id"])
        )
    for chunk in _chunks(list(first_by_member)):
        result = await session.execute(
            select(Member.external_member_id, Member.id).where(Member.external_member_id.in_(chunk))
        )
        ctx.member_ids.update(dict(result.all()))

    # A payer policy number identifies exactly one member; existing ownership wins.
    policy_keys = {(ctx.payer_ids[normalize_name(r.payer_name)], r.policy_number) for r in rows}
    owners: dict[tuple[int, str], uuid.UUID] = {}
    for chunk in _chunks(list(policy_keys)):
        result = await session.execute(
            select(MemberPolicy.payer_id, MemberPolicy.policy_number, MemberPolicy.member_id).where(
                tuple_(MemberPolicy.payer_id, MemberPolicy.policy_number).in_(chunk)
            )
        )
        owners.update({(p, n): m for p, n, m in result})

    accepted: list[ParsedRow] = []
    errors: list[RowIssue] = []
    new_policies: dict[tuple[int, str], uuid.UUID] = {}
    for r in rows:
        key = (ctx.payer_ids[normalize_name(r.payer_name)], r.policy_number)
        member_id = ctx.member_ids[r.member_id]
        owner = owners.get(key) or new_policies.get(key)
        if owner is None:
            new_policies[key] = member_id
        elif owner != member_id:
            errors.append(
                RowIssue(
                    r.row_number,
                    "policy_number",
                    f"Policy {r.policy_number} for {r.payer_name} "
                    "already belongs to another member",
                )
            )
            continue
        accepted.append(r)

    for chunk in _chunks(list(new_policies.items())):
        await session.execute(
            insert(MemberPolicy)
            .values([{"payer_id": p, "policy_number": n, "member_id": m} for (p, n), m in chunk])
            .on_conflict_do_nothing(index_elements=["payer_id", "policy_number"])
        )
    return accepted, errors


async def _member_consistency_warnings(
    session: AsyncSession, rows: list[ParsedRow], ctx: _Context
) -> list[RowIssue]:
    """Canonical member demographics are not overwritten by later files; flag differences."""
    if not rows:
        return []
    stored: dict[str, tuple[str, Any]] = {}
    for chunk in _chunks(list({r.member_id for r in rows})):
        result = await session.execute(
            select(Member.external_member_id, Member.member_name, Member.date_of_birth).where(
                Member.external_member_id.in_(chunk)
            )
        )
        stored.update({ext: (name, dob) for ext, name, dob in result})

    warnings = []
    for r in rows:
        name, dob = stored[r.member_id]
        if normalize_name(name) != normalize_name(r.member_name) or (
            r.date_of_birth and dob and dob != r.date_of_birth
        ):
            warnings.append(
                RowIssue(
                    r.row_number,
                    "member_id",
                    f"{r.member_id} name/DOB differs from the existing member record",
                )
            )
    return warnings


def _opportunity_key(r: ParsedRow, ctx: _Context) -> tuple[uuid.UUID, int, int, int, str]:
    return (
        ctx.member_ids[r.member_id],
        ctx.payer_ids[normalize_name(r.payer_name)],
        ctx.provider_ids[(normalize_name(r.provider_group), normalize_name(r.provider_name))],
        r.performance_year,
        r.icd10_code,
    )


async def _upsert_opportunities(
    session: AsyncSession, rows: list[ParsedRow], ctx: _Context
) -> tuple[int, dict[tuple, uuid.UUID]]:
    by_key: dict[tuple, ParsedRow] = {}
    for r in rows:
        key = _opportunity_key(r, ctx)
        if key not in by_key or (by_key[key].icd10_description is None and r.icd10_description):
            by_key[key] = r

    new_count = 0
    for chunk in _chunks(list(by_key.items())):
        result = await session.execute(
            insert(Opportunity)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "member_id": m,
                        "payer_id": p,
                        "provider_id": pr,
                        "performance_year": y,
                        "icd10_code": c,
                        "icd10_description": r.icd10_description,
                    }
                    for (m, p, pr, y, c), r in chunk
                ]
            )
            .on_conflict_do_nothing(constraint="uq_opportunity_business_key")
            .returning(Opportunity.id)
        )
        new_count += len(result.all())

    ids: dict[tuple, uuid.UUID] = {}
    cols = (
        Opportunity.member_id,
        Opportunity.payer_id,
        Opportunity.provider_id,
        Opportunity.performance_year,
        Opportunity.icd10_code,
    )
    for chunk in _chunks(list(by_key)):
        result = await session.execute(
            select(*cols, Opportunity.id).where(tuple_(*cols).in_(chunk))
        )
        ids.update({tuple(row[:5]): row[5] for row in result})
    return new_count, ids


async def _insert_source_records(
    session: AsyncSession,
    rows: list[ParsedRow],
    ctx: _Context,
    opp_ids: dict[tuple, uuid.UUID],
    batch_id: uuid.UUID,
) -> int:
    inserted = 0
    for chunk in _chunks(rows):
        result = await session.execute(
            insert(SourceRecord)
            .values(
                [
                    {
                        "upload_batch_id": batch_id,
                        "opportunity_id": opp_ids[_opportunity_key(r, ctx)],
                        "source_file": r.source_file,
                        "source_row_number": r.row_number,
                        "row_fingerprint": r.fingerprint,
                        "policy_number": r.policy_number,
                        "initiative": r.initiative,
                        "evidence": r.evidence,
                        "last_dos": r.last_dos,
                        "reported_hcc_code": r.hcc_code,
                        "reported_hcc_description": r.hcc_description,
                        "raw_payload": r.raw,
                    }
                    for r in chunk
                ]
            )
            .on_conflict_do_nothing(constraint="uq_source_file_fingerprint")
            .returning(SourceRecord.id)
        )
        inserted += len(result.all())
    return inserted
