from sqlalchemy import func, select

from app.core.config import REPO_ROOT
from app.core.database import SessionLocal
from app.models import Member, MemberPolicy, Opportunity, Payer, SourceRecord, UserRole
from app.services.csv_parser import EXPECTED_COLUMNS
from tests.conftest import login

SAMPLE = (REPO_ROOT / "sample_data" / "sample_mra_data.csv").read_bytes()
HEADER = ",".join(EXPECTED_COLUMNS)


async def upload(client, content: bytes, filename: str = "sample_mra_data.csv"):
    return await client.post("/api/v1/imports", files={"file": (filename, content, "text/csv")})


async def as_admin(client, make_user):
    await make_user("admin@x.test", role=UserRole.ADMIN)
    await login(client, "admin@x.test")


async def scalar(stmt):
    async with SessionLocal() as session:
        return await session.scalar(stmt)


async def opportunities_for(external_id: str, icd10: str):
    async with SessionLocal() as session:
        result = await session.execute(
            select(Opportunity, Payer.display_name)
            .join(Member, Member.id == Opportunity.member_id)
            .join(Payer, Payer.id == Opportunity.payer_id)
            .where(Member.external_member_id == external_id, Opportunity.icd10_code == icd10)
            .order_by(Opportunity.performance_year, Payer.display_name)
        )
        return result.all()


async def test_sample_import_resolves_identity_dedupes_and_flags_conflicts(client, make_user):
    await as_admin(client, make_user)

    response = await upload(client, SAMPLE)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["total_rows"] == 128
    assert body["rejected_rows"] == 0
    assert body["inserted_source_rows"] + body["duplicate_source_rows"] == 128
    assert body["uploaded_by_email"] == "admin@x.test"

    # Identity: 32 canonical members; dual-payer MEM015 is one member with two policies.
    assert await scalar(select(func.count()).select_from(Member)) == 32
    mem015_policies = await scalar(
        select(func.count())
        .select_from(MemberPolicy)
        .join(Member)
        .where(Member.external_member_id == "MEM015")
    )
    assert mem015_policies == 2

    # Multi-source: MEM001 E119 PY2025 appears in MAO-004 and gap files -> one opportunity
    # with two evidence rows; the PY2024 record stays a separate year-specific opportunity.
    e119 = await opportunities_for("MEM001", "E119")
    assert [o.performance_year for o, _ in e119] == [2024, 2025]
    py2025_sources = await scalar(
        select(func.count()).where(SourceRecord.opportunity_id == e119[1][0].id)
    )
    assert py2025_sources == 2

    # Conflicting cross-payer HCC for I2510: each payer keeps its own assertion, both flagged.
    i2510 = await opportunities_for("MEM015", "I2510")
    assert {(payer, o.hcc_code, o.hcc_conflict) for o, payer in i2510} == {
        ("Aetna", "226", True),
        ("CarePlus", "222", True),
    }

    # Non-HCC with missing last_dos and missing description is accepted, not a conflict.
    [(e785, _)] = await opportunities_for("MEM032", "E785")
    assert e785.hcc_code is None and e785.hcc_conflict is False

    quoted = await scalar(
        select(SourceRecord.evidence).where(SourceRecord.evidence.like("Suspect COPD - prior%"))
    )
    assert quoted == "Suspect COPD - prior year dx, no 2025 claim"


async def test_reupload_is_idempotent_but_recorded_in_history(client, make_user):
    await as_admin(client, make_user)
    first = (await upload(client, SAMPLE)).json()
    opportunities = await scalar(select(func.count()).select_from(Opportunity))

    second = (await upload(client, SAMPLE)).json()

    assert second["status"] == "COMPLETED"
    assert second["inserted_source_rows"] == 0
    assert second["duplicate_source_rows"] == first["inserted_source_rows"]
    assert second["new_opportunities"] == 0
    assert await scalar(select(func.count()).select_from(Opportunity)) == opportunities

    history = (await client.get("/api/v1/imports")).json()
    assert [h["id"] for h in history["items"]] == [second["id"], first["id"]]


async def test_missing_columns_rejects_file_without_touching_domain_tables(client, make_user):
    await as_admin(client, make_user)
    content = SAMPLE.replace(b",hcc_code,", b",hcc,", 1)

    response = await upload(client, content)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "MISSING_COLUMNS"
    assert error["details"]["missing_columns"] == ["hcc_code"]
    assert await scalar(select(func.count()).select_from(Member)) == 0

    attempt = (await client.get(f"/api/v1/imports/{error['details']['upload_id']}")).json()
    assert attempt["status"] == "FAILED"
    assert attempt["missing_columns"] == ["hcc_code"]


async def test_policy_owned_by_another_member_is_rejected_per_row(client, make_user):
    await as_admin(client, make_user)
    good = (
        "MEM900,P1,Ann Lee,1/1/1950,Aetna,Palm Medical Group,Dr. Garcia,E119,,37,,"
        "HCC Gap,,,aetna_hcc_gaps_202501.csv"
    )
    hijack = good.replace("MEM900,P1,Ann Lee", "MEM901,P1,Bob Ray").replace("E119", "I10")
    content = "\n".join([HEADER, good, hijack]).encode()

    body = (await upload(client, content, "small.csv")).json()

    assert body["status"] == "COMPLETED_WITH_ERRORS"
    assert body["inserted_source_rows"] == 1 and body["rejected_rows"] == 1
    assert body["errors"] == [
        {
            "row": 3,
            "field": "policy_number",
            "reason": "Policy P1 for Aetna already belongs to another member",
        }
    ]


async def test_only_admins_can_import(client, make_user):
    await make_user("coder@x.test", providers=("dr. garcia",))
    await login(client, "coder@x.test")

    assert (await upload(client, SAMPLE)).status_code == 403
    assert (await client.get("/api/v1/imports")).status_code == 403


async def test_rejects_non_csv_and_non_utf8(client, make_user):
    await as_admin(client, make_user)

    assert (await upload(client, SAMPLE, "data.xlsx")).json()["error"]["code"] == "INVALID_FILE"
    latin1 = (HEADER + "\nMEM1,P,Jos\xe9").encode("latin-1")
    response = await upload(client, latin1)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE"
