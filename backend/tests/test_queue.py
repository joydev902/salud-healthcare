from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models import Member, Opportunity, Provider, UserProviderAssignment, UserRole
from app.services.normalize import normalize_name
from tests.conftest import login
from tests.test_ingestion import SAMPLE, upload

ALL_PROVIDERS = ("dr. garcia", "dr. thompson", "dr. patel", "dr. nguyen")


async def seed_sample(client, make_user):
    await make_user("admin@x.test", role=UserRole.ADMIN, providers=ALL_PROVIDERS)
    await login(client, "admin@x.test")
    assert (await upload(client, SAMPLE)).status_code == 201


async def as_coder(client, make_user, *providers: str, email: str = "coder@x.test"):
    user = await make_user(email, providers=providers)
    await login(client, email)
    return user


async def member_id(external_id: str) -> str:
    async with SessionLocal() as session:
        return str(
            await session.scalar(select(Member.id).where(Member.external_member_id == external_id))
        )


async def opportunity_ids_for_provider(name: str) -> list[str]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(Opportunity.id)
            .join(Provider, Provider.id == Opportunity.provider_id)
            .where(Provider.normalized_name == normalize_name(name))
        )
        return [str(r) for r in rows]


async def all_pages(client, params: dict) -> list[dict]:
    items, cursor = [], None
    while True:
        query = {**params, **({"cursor": cursor} if cursor else {})}
        body = (await client.get("/api/v1/members", params=query)).json()
        items += body["items"]
        if not body["has_more"]:
            assert body["next_cursor"] is None
            return items
        cursor = body["next_cursor"]


async def test_queue_shows_only_assigned_members_with_stable_keyset_pages(client, make_user):
    await seed_sample(client, make_user)
    await as_coder(client, make_user, "dr. garcia", "dr. thompson")

    items = await all_pages(client, {"limit": 5})

    external_ids = [i["external_member_id"] for i in items]
    assert len(items) == 13
    assert external_ids == sorted(set(external_ids))
    assert {p for i in items for p in i["providers"]} == {"Dr. Garcia", "Dr. Thompson"}
    assert sum(i["matched_opportunity_count"] for i in items) == 50
    # Nothing is dispositioned yet, so every matched opportunity is still open.
    assert all(i["open_opportunity_count"] == i["matched_opportunity_count"] for i in items)


async def test_filters_compose_and_initiative_counts_each_opportunity_once(client, make_user):
    await seed_sample(client, make_user)

    audit = await all_pages(client, {"initiative": "Audit", "limit": 100})
    assert sum(i["matched_opportunity_count"] for i in audit) == 12

    providers = (await client.get("/api/v1/providers")).json()
    garcia = next(p["id"] for p in providers if p["name"] == "Dr. Garcia")
    by_provider = await all_pages(client, {"provider_id": garcia, "limit": 100})
    assert len(by_provider) == 7
    assert sum(i["matched_opportunity_count"] for i in by_provider) == 27

    py2024 = await all_pages(client, {"performance_year": 2024, "limit": 100})
    assert sum(i["matched_opportunity_count"] for i in py2024) == 14

    payers = (await client.get("/api/v1/payers")).json()
    aetna = next(p["id"] for p in payers if p["name"] == "Aetna")
    combined = await all_pages(
        client, {"payer_id": aetna, "provider_id": garcia, "disposition": "OPEN", "limit": 100}
    )
    assert {p for i in combined for p in i["payers"]} <= {"Aetna"}

    confirmed = (await client.get("/api/v1/members", params={"disposition": "CONFIRMED"})).json()
    assert confirmed == {"items": [], "next_cursor": None, "has_more": False}


async def test_member_search_and_cursor_bound_to_filters(client, make_user):
    await seed_sample(client, make_user)

    found = (await client.get("/api/v1/members", params={"q": "mem01"})).json()
    assert [i["external_member_id"] for i in found["items"]] == [f"MEM01{n}" for n in range(10)]

    first = (await client.get("/api/v1/members", params={"limit": 2})).json()
    reused = await client.get(
        "/api/v1/members", params={"limit": 2, "cursor": first["next_cursor"], "q": "x"}
    )
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "INVALID_CURSOR"


async def test_unassigned_provider_is_blocked_everywhere(client, make_user):
    await seed_sample(client, make_user)
    await as_coder(client, make_user, "dr. garcia")
    providers = {p["name"]: p["id"] for p in (await client.get("/api/v1/providers")).json()}
    assert list(providers) == ["Dr. Garcia"]

    patel_opportunity = (await opportunity_ids_for_provider("Dr. Patel"))[0]
    async with SessionLocal() as session:
        patel_member = str(
            await session.scalar(
                select(Opportunity.member_id).where(Opportunity.id == patel_opportunity)
            )
        )
        patel_id = await session.scalar(
            select(Provider.id).where(Provider.normalized_name == "dr. patel")
        )

    filtered = await client.get("/api/v1/members", params={"provider_id": patel_id})
    assert filtered.status_code == 403
    for path in (
        f"/api/v1/members/{patel_member}",
        f"/api/v1/members/{patel_member}/opportunities",
        f"/api/v1/opportunities/{patel_opportunity}",
    ):
        response = await client.get(path)
        assert response.status_code == 404, path
        assert "MEM" not in response.text


async def test_revoking_assignment_takes_effect_on_next_request(client, make_user):
    await seed_sample(client, make_user)
    coder = await as_coder(client, make_user, "dr. garcia")
    opportunity = (await opportunity_ids_for_provider("Dr. Garcia"))[0]
    assert (await client.get(f"/api/v1/opportunities/{opportunity}")).status_code == 200

    async with SessionLocal() as session, session.begin():
        await session.execute(
            delete(UserProviderAssignment).where(UserProviderAssignment.user_id == coder.id)
        )

    assert (await client.get(f"/api/v1/opportunities/{opportunity}")).status_code == 404
    assert (await client.get("/api/v1/members")).json()["items"] == []


async def test_member_drilldown_shows_evidence_and_hcc_conflict_candidates(client, make_user):
    await seed_sample(client, make_user)
    await as_coder(client, make_user, "dr. nguyen")
    mem015 = await member_id("MEM015")

    member = (await client.get(f"/api/v1/members/{mem015}")).json()
    assert member["external_member_id"] == "MEM015"
    assert {p["payer_name"] for p in member["policies"]} == {"Aetna", "CarePlus"}
    assert [p["name"] for p in member["providers"]] == ["Dr. Nguyen"]

    opportunities = (await client.get(f"/api/v1/members/{mem015}/opportunities")).json()
    assert len(opportunities) == member["total_opportunity_count"]
    i2510 = [o for o in opportunities if o["icd10_code"] == "I2510"]
    assert {o["payer"]["name"] for o in i2510} == {"Aetna", "CarePlus"}
    assert all(o["hcc_conflict"] and o["source_count"] >= 1 for o in i2510)

    aetna = next(o for o in i2510 if o["payer"]["name"] == "Aetna")
    detail = (await client.get(f"/api/v1/opportunities/{aetna['id']}")).json()
    assert detail["member"]["external_member_id"] == "MEM015"
    assert detail["current_disposition"] == "OPEN"
    assert len(detail["sources"]) == detail["source_count"]
    assert [(c["payer_name"], c["hcc_code"]) for c in detail["hcc_candidates"]] == [
        ("CarePlus", "222")
    ]


async def test_reference_options_are_scoped(client, make_user):
    await seed_sample(client, make_user)
    await as_coder(client, make_user, "dr. garcia")

    assert (await client.get("/api/v1/performance-years")).json() in ([2025, 2024], [2025])
    initiatives = (await client.get("/api/v1/initiatives")).json()
    assert initiatives == sorted(initiatives) and initiatives

    await as_coder(client, make_user, email="nobody@x.test")
    assert (await client.get("/api/v1/initiatives")).json() == []
    assert (await client.get("/api/v1/members")).json()["items"] == []


async def test_queue_requires_authentication(client):
    assert (await client.get("/api/v1/members")).status_code == 401
    assert (await client.get("/api/v1/providers")).status_code == 401
