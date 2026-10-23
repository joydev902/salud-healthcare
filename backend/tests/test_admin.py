from app.models import UserRole
from tests.conftest import TEST_PASSWORD, login

NEW_PASSWORD = "another-long-password"


async def as_admin(client, make_user):
    admin = await make_user("admin@x.test", role=UserRole.ADMIN)
    await login(client, "admin@x.test")
    return admin


async def provider_id(client, name: str) -> int:
    providers = (await client.get("/api/v1/admin/providers")).json()
    return next(p["id"] for p in providers if p["name"] == name)


async def test_admin_creates_coder_who_can_sign_in_with_assigned_scope(client, make_user):
    await as_admin(client, make_user)
    garcia = await provider_id(client, "Dr. Garcia")

    created = await client.post(
        "/api/v1/admin/users",
        json={
            "email": " New.Coder@X.test ",
            "full_name": "New Coder",
            "role": "CODER",
            "password": NEW_PASSWORD,
            "provider_ids": [garcia],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["email"] == "new.coder@x.test"
    assert [p["name"] for p in body["providers"]] == ["Dr. Garcia"]

    duplicate = await client.post(
        "/api/v1/admin/users",
        json={
            **{"full_name": "x", "role": "CODER", "password": NEW_PASSWORD},
            "email": "NEW.coder@x.test",
        },
    )
    assert duplicate.status_code == 409

    me = (await login(client, "new.coder@x.test", NEW_PASSWORD)).json()
    assert me["role"] == "CODER" and [p["name"] for p in me["providers"]] == ["Dr. Garcia"]


async def test_replace_assignments_and_deactivate_take_effect_immediately(client, make_user):
    await as_admin(client, make_user)
    coder = await make_user("coder@x.test", providers=("dr. garcia",))
    patel = await provider_id(client, "Dr. Patel")
    nguyen = await provider_id(client, "Dr. Nguyen")

    replaced = await client.put(
        f"/api/v1/admin/users/{coder.id}/providers", json={"provider_ids": [patel, nguyen]}
    )
    assert [p["name"] for p in replaced.json()] == ["Dr. Nguyen", "Dr. Patel"]
    assignments = (await client.get(f"/api/v1/admin/users/{coder.id}/providers")).json()
    assert {p["id"] for p in assignments} == {patel, nguyen}

    unknown = await client.put(
        f"/api/v1/admin/users/{coder.id}/providers", json={"provider_ids": [patel, 99999]}
    )
    assert unknown.status_code == 422
    assert unknown.json()["error"]["details"] == {"provider_ids": [99999]}

    deactivated = await client.patch(f"/api/v1/admin/users/{coder.id}", json={"is_active": False})
    assert deactivated.json()["is_active"] is False

    # Sign in as the coder in a fresh session: the deactivated account is refused.
    assert (await login(client, "coder@x.test")).status_code == 401


async def test_deactivation_ends_existing_sessions(client, make_user):
    coder = await make_user("coder@x.test", providers=("dr. garcia",))
    await login(client, "coder@x.test")
    assert (await client.get("/api/v1/auth/me")).status_code == 200

    await make_user("admin@x.test", role=UserRole.ADMIN)
    coder_cookie = client.cookies.get("mra_session")
    await login(client, "admin@x.test")
    await client.patch(f"/api/v1/admin/users/{coder.id}", json={"is_active": False})

    client.cookies.set("mra_session", coder_cookie)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_admin_cannot_lock_themselves_out(client, make_user):
    admin = await as_admin(client, make_user)

    for change in ({"is_active": False}, {"role": "CODER"}):
        response = await client.patch(f"/api/v1/admin/users/{admin.id}", json=change)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SELF_LOCKOUT"

    renamed = await client.patch(f"/api/v1/admin/users/{admin.id}", json={"full_name": "Boss"})
    assert renamed.json()["full_name"] == "Boss"


async def test_password_reset_and_validation(client, make_user):
    await as_admin(client, make_user)
    coder = await make_user("coder@x.test")

    weak = await client.patch(f"/api/v1/admin/users/{coder.id}", json={"password": "pw-9x7"})
    assert weak.status_code == 422
    assert "pw-9x7" not in weak.text
    bad_email = await client.post(
        "/api/v1/admin/users",
        json={"email": "nope", "full_name": "x", "role": "CODER", "password": NEW_PASSWORD},
    )
    assert bad_email.status_code == 422

    await client.patch(f"/api/v1/admin/users/{coder.id}", json={"password": NEW_PASSWORD})
    assert (await login(client, "coder@x.test", TEST_PASSWORD)).status_code == 401
    assert (await login(client, "coder@x.test", NEW_PASSWORD)).status_code == 200


async def test_user_list_filters_and_pages(client, make_user):
    await as_admin(client, make_user)
    for n in range(5):
        await make_user(f"coder{n}@x.test")

    first = (await client.get("/api/v1/admin/users", params={"limit": 4})).json()
    second = (
        await client.get("/api/v1/admin/users", params={"limit": 4, "cursor": first["next_cursor"]})
    ).json()
    emails = [u["email"] for u in first["items"] + second["items"]]
    assert emails == sorted(emails) and len(emails) == 6 and not second["has_more"]

    coders = (await client.get("/api/v1/admin/users", params={"role": "CODER"})).json()
    assert len(coders["items"]) == 5
    found = (await client.get("/api/v1/admin/users", params={"q": "coder3"})).json()
    assert [u["email"] for u in found["items"]] == ["coder3@x.test"]


async def test_admin_endpoints_reject_coders(client, make_user):
    coder = await make_user("coder@x.test")
    await login(client, "coder@x.test")

    assert (await client.get("/api/v1/admin/users")).status_code == 403
    assert (await client.get("/api/v1/admin/providers")).status_code == 403
    response = await client.put(
        f"/api/v1/admin/users/{coder.id}/providers", json={"provider_ids": []}
    )
    assert response.status_code == 403
