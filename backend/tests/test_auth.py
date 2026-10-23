from sqlalchemy import delete, update

from app.core.database import SessionLocal
from app.core.middleware import CSRF_HEADER
from app.models import User, UserProviderAssignment
from tests.conftest import login


async def test_login_sets_httponly_cookie_and_me_returns_scope(client, make_user):
    await make_user("coder@x.test", providers=("dr. garcia", "dr. thompson"))

    response = await login(client, "CODER@x.test")

    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=strict" in set_cookie
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["role"] == "CODER"
    assert sorted(p["name"] for p in me["providers"]) == ["Dr. Garcia", "Dr. Thompson"]


async def test_bad_credentials_are_indistinguishable(client, make_user):
    await make_user("coder@x.test")
    await make_user("inactive@x.test", is_active=False)

    responses = [
        await login(client, "coder@x.test", "wrong-password"),
        await login(client, "nobody@x.test"),
        await login(client, "inactive@x.test"),
    ]

    for r in responses:
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "UNAUTHENTICATED"
        assert r.json()["error"]["message"] == "Invalid email or password"
        assert r.json()["error"]["request_id"]


async def test_me_requires_session(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_deactivation_and_revocation_apply_to_existing_session(client, make_user):
    user = await make_user("coder@x.test", providers=("dr. patel",))
    assert (await login(client, "coder@x.test")).status_code == 200

    async with SessionLocal() as session, session.begin():
        await session.execute(
            delete(UserProviderAssignment).where(UserProviderAssignment.user_id == user.id)
        )
    assert (await client.get("/api/v1/auth/me")).json()["providers"] == []

    async with SessionLocal() as session, session.begin():
        await session.execute(update(User).where(User.id == user.id).values(is_active=False))
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_state_changing_request_with_cookie_requires_csrf_header(client, make_user):
    await make_user("coder@x.test")
    await login(client, "coder@x.test")

    response = await client.post("/api/v1/auth/logout", headers={CSRF_HEADER: ""})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_HEADER_MISSING"

    assert (await client.post("/api/v1/auth/logout")).status_code == 204
