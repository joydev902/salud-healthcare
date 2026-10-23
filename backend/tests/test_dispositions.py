import asyncio

import httpx2
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.middleware import CSRF_HEADER
from app.main import create_app
from app.models import DispositionHistory, Opportunity
from tests.conftest import login
from tests.test_queue import as_coder, opportunity_ids_for_provider, seed_sample

JUSTIFICATION = "Current-year progress note documents CAD with treatment plan."


async def decide(client, opportunity_id: str, disposition: str, version: int, note=JUSTIFICATION):
    return await client.post(
        f"/api/v1/opportunities/{opportunity_id}/dispositions",
        json={"new_disposition": disposition, "justification": note, "expected_version": version},
    )


async def garcia_opportunity() -> str:
    return (await opportunity_ids_for_provider("Dr. Garcia"))[0]


async def test_each_change_is_recorded_with_actor_previous_and_new_values(client, make_user):
    await seed_sample(client, make_user)
    await as_coder(client, make_user, "dr. garcia")
    opp = await garcia_opportunity()

    first = await decide(client, opp, "PENDING_CHART", 0, "  Request the 2025 chart note.  ")
    assert first.status_code == 200
    assert first.json()["current_disposition"] == "PENDING_CHART"
    assert first.json()["disposition_version"] == 1

    second = await decide(client, opp, "CONFIRMED", 1)
    assert second.json()["disposition_version"] == 2

    detail = (await client.get(f"/api/v1/opportunities/{opp}")).json()
    assert detail["current_disposition"] == "CONFIRMED"
    assert detail["current_note"] == JUSTIFICATION
    assert detail["last_disposition_by_email"] == "coder@x.test"

    history = (await client.get(f"/api/v1/opportunities/{opp}/dispositions")).json()
    assert [(h["old_status"], h["new_status"], h["new_version"]) for h in history] == [
        ("PENDING_CHART", "CONFIRMED", 2),
        ("OPEN", "PENDING_CHART", 1),
    ]
    assert history[1]["note"] == "Request the 2025 chart note."
    assert {h["changed_by_email"] for h in history} == {"coder@x.test"}

    queue = (await client.get("/api/v1/members", params={"disposition": "CONFIRMED"})).json()
    assert [m["matched_opportunity_count"] for m in queue["items"]] == [1]
    assert queue["items"][0]["open_opportunity_count"] == 0


async def test_stale_version_is_rejected_with_current_state(client, make_user):
    await seed_sample(client, make_user)
    await as_coder(client, make_user, "dr. garcia")
    opp = await garcia_opportunity()
    await decide(client, opp, "DENIED", 0)

    stale = await decide(client, opp, "CONFIRMED", 0)

    assert stale.status_code == 409
    error = stale.json()["error"]
    assert error["code"] == "STALE_VERSION"
    assert error["details"]["current_disposition"] == "DENIED"
    assert error["details"]["disposition_version"] == 1
    assert error["details"]["last_disposition_by_email"] == "coder@x.test"
    assert len((await client.get(f"/api/v1/opportunities/{opp}/dispositions")).json()) == 1


async def test_concurrent_writers_cannot_both_win(client, make_user):
    await seed_sample(client, make_user)
    await make_user("one@x.test", providers=("dr. garcia",))
    await make_user("two@x.test", providers=("dr. garcia",))
    opp = await garcia_opportunity()

    async def coder_client(email: str) -> httpx2.AsyncClient:
        c = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=create_app()),
            base_url="http://test",
            headers={CSRF_HEADER: "fetch"},
        )
        await login(c, email)
        return c

    one, two = await coder_client("one@x.test"), await coder_client("two@x.test")
    try:
        results = await asyncio.gather(
            decide(one, opp, "CONFIRMED", 0), decide(two, opp, "DENIED", 0)
        )
    finally:
        await one.aclose()
        await two.aclose()

    assert sorted(r.status_code for r in results) == [200, 409]
    async with SessionLocal() as session:
        assert (
            await session.scalar(
                select(func.count()).where(DispositionHistory.opportunity_id == opp)
            )
            == 1
        )
        assert (await session.get(Opportunity, opp)).disposition_version == 1


async def test_justification_and_disposition_are_validated(client, make_user):
    await seed_sample(client, make_user)
    await as_coder(client, make_user, "dr. garcia")
    opp = await garcia_opportunity()

    for disposition, note in (("CONFIRMED", "   "), ("CONFIRMED", "ok"), ("OPEN", JUSTIFICATION)):
        response = await decide(client, opp, disposition, 0, note)
        assert response.status_code == 422, (disposition, note)

    assert (await decide(client, opp, "MAYBE", 0)).status_code == 422
    assert (await client.get(f"/api/v1/opportunities/{opp}/dispositions")).json() == []


async def test_only_assigned_coders_can_decide(client, make_user):
    await seed_sample(client, make_user)
    patel_opp = (await opportunity_ids_for_provider("Dr. Patel"))[0]

    # The admin can see the opportunity, but only a coder can record the decision.
    admin_attempt = await decide(client, patel_opp, "CONFIRMED", 0)
    assert admin_attempt.status_code == 403
    assert (await client.get(f"/api/v1/opportunities/{patel_opp}/dispositions")).status_code == 200

    await as_coder(client, make_user, "dr. garcia")
    assert (await decide(client, patel_opp, "CONFIRMED", 0)).status_code == 404
    history = await client.get(f"/api/v1/opportunities/{patel_opp}/dispositions")
    assert history.status_code == 404


async def test_writes_require_csrf_header(client, make_user):
    await seed_sample(client, make_user)
    await as_coder(client, make_user, "dr. garcia")
    opp = await garcia_opportunity()

    response = await client.post(
        f"/api/v1/opportunities/{opp}/dispositions",
        json={
            "new_disposition": "CONFIRMED",
            "justification": JUSTIFICATION,
            "expected_version": 0,
        },
        headers={CSRF_HEADER: ""},
    )
    assert response.status_code == 403
