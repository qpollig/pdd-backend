"""Связывание/отвязка способов входа: /api/v1/auth/identities*.

Все ручки требуют Bearer-токен. Автосвязывания по email нет и не проверяется —
проверяется, что связывание идёт ТОЛЬКО явным действием залогиненного пользователя.
"""

from tests.conftest import auth_header


async def _oauth_login(client, provider: str, code: str) -> tuple[str, str]:
    """mock-OAuth логин (conftest: OAUTH_ALLOW_MOCK=true). Возвращает (token, user_id)."""
    r = await client.post(f"/api/v1/auth/oauth/{provider}", json={"code": code})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["access_token"], body["user"]["id"]


async def _register(client, email: str, password: str, name: str = "U") -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password, "name": name}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], r.json()["user"]["id"]


# ── GET /identities ─────────────────────────────────────────────────────────────────────────
async def test_identity_list_shape(client):
    token, _uid = await _oauth_login(client, "yandex", "shape-code")
    r = await client.get("/api/v1/auth/identities", headers=auth_header(token))
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) and len(body) == 1
    assert set(body[0]) == {"type", "identifier", "created_at"}
    assert body[0]["type"] == "yandex"
    assert body[0]["identifier"].startswith("mock-yandex-")


async def test_identities_endpoints_require_bearer(client):
    assert (await client.get("/api/v1/auth/identities")).status_code == 401
    assert (
        await client.post("/api/v1/auth/identities/oauth/yandex", json={"code": "x"})
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/identities/password",
            json={"email": "x@example.com", "password": "12345678"},
        )
    ).status_code == 401
    assert (await client.delete("/api/v1/auth/identities/yandex")).status_code == 401


# ── POST /identities/password ──────────────────────────────────────────────────────────────
async def test_link_password_then_both_methods_reach_same_user(client):
    token, uid = await _oauth_login(client, "yandex", "link-scenario-code")

    r = await client.post(
        "/api/v1/auth/identities/password",
        json={"email": "linked@example.com", "password": "linked-pass-123"},
        headers=auth_header(token),
    )
    assert r.status_code == 200, r.text
    assert {i["type"] for i in r.json()} == {"yandex", "password"}

    # вход по паролю -> тот же user_id
    by_pw = await client.post(
        "/api/v1/auth/login", json={"email": "linked@example.com", "password": "linked-pass-123"}
    )
    assert by_pw.status_code == 200
    me_pw = await client.get("/api/v1/users/me", headers=auth_header(by_pw.json()["access_token"]))
    assert me_pw.json()["id"] == uid

    # старый Yandex mock-код -> тот же user_id
    by_oauth = await client.post("/api/v1/auth/oauth/yandex", json={"code": "link-scenario-code"})
    assert by_oauth.json()["user"]["id"] == uid


async def test_link_password_email_taken_by_other_returns_409(client):
    await _register(client, "taken@example.com", "aaa-pass-123")
    token_b, _uid_b = await _oauth_login(client, "yandex", "user-b-code")

    r = await client.post(
        "/api/v1/auth/identities/password",
        json={"email": "TAKEN@Example.com", "password": "bbb-pass-123"},  # тот же email, иной регистр
        headers=auth_header(token_b),
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "EMAIL_ALREADY_REGISTERED"


async def test_link_password_when_already_has_password_returns_409(client):
    token, _uid = await _register(client, "haspw@example.com", "has-pass-123")
    r = await client.post(
        "/api/v1/auth/identities/password",
        json={"email": "haspw-second@example.com", "password": "other-pass-123"},
        headers=auth_header(token),
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "PASSWORD_ALREADY_SET"


async def test_link_password_invalid_body_returns_422(client):
    token, _uid = await _oauth_login(client, "yandex", "bad-body-code")
    r = await client.post(
        "/api/v1/auth/identities/password",
        json={"email": "not-an-email", "password": "short"},
        headers=auth_header(token),
    )
    assert r.status_code == 422


# ── POST /identities/oauth/{provider} ──────────────────────────────────────────────────────
async def test_link_fresh_oauth_to_password_account(client):
    token, uid = await _register(client, "reg-then-link@example.com", "reg-pass-123")

    r = await client.post(
        "/api/v1/auth/identities/oauth/vk",
        json={"code": "fresh-vk-for-pw-user"},
        headers=auth_header(token),
    )
    assert r.status_code == 200, r.text
    assert {i["type"] for i in r.json()} == {"password", "vk"}

    # vk-логин тем же кодом теперь ведёт на того же пользователя
    by_vk = await client.post("/api/v1/auth/oauth/vk", json={"code": "fresh-vk-for-pw-user"})
    assert by_vk.json()["user"]["id"] == uid


async def test_link_oauth_code_owned_by_other_user_returns_409_and_does_not_rebind(client):
    _token_a, uid_a = await _oauth_login(client, "yandex", "code-of-user-A")
    token_b, uid_b = await _oauth_login(client, "vk", "code-of-user-B")
    assert uid_a != uid_b

    r = await client.post(
        "/api/v1/auth/identities/oauth/yandex",
        json={"code": "code-of-user-A"},  # это Yandex пользователя A
        headers=auth_header(token_b),
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "IDENTITY_ALREADY_LINKED"

    # A по-прежнему владеет этим Yandex — не перепривязано к B
    relogin = await client.post("/api/v1/auth/oauth/yandex", json={"code": "code-of-user-A"})
    assert relogin.json()["user"]["id"] == uid_a
    # у B ничего не добавилось
    b_ids = await client.get("/api/v1/auth/identities", headers=auth_header(token_b))
    assert [i["type"] for i in b_ids.json()] == ["vk"]


async def test_link_oauth_same_code_already_linked_to_self_is_idempotent(client):
    token, _uid = await _oauth_login(client, "yandex", "self-idem-code")
    before = (await client.get("/api/v1/auth/identities", headers=auth_header(token))).json()

    r = await client.post(
        "/api/v1/auth/identities/oauth/yandex",
        json={"code": "self-idem-code"},
        headers=auth_header(token),
    )
    assert r.status_code == 200
    assert r.json() == before  # ничего не поменялось
    assert len(r.json()) == 1


# ── DELETE /identities/{type} ──────────────────────────────────────────────────────────────
async def test_unlink_last_identity_is_forbidden(client):
    token, _uid = await _oauth_login(client, "yandex", "solo-user-code")
    r = await client.delete("/api/v1/auth/identities/yandex", headers=auth_header(token))
    assert r.status_code == 409
    assert r.json()["detail"] == "CANNOT_UNLINK_LAST_IDENTITY"
    still = await client.get("/api/v1/auth/identities", headers=auth_header(token))
    assert [i["type"] for i in still.json()] == ["yandex"]


async def test_unlink_one_of_two_keeps_the_other(client):
    token, _uid = await _oauth_login(client, "yandex", "two-methods-code")
    await client.post(
        "/api/v1/auth/identities/password",
        json={"email": "two@example.com", "password": "two-pass-123"},
        headers=auth_header(token),
    )

    r = await client.delete("/api/v1/auth/identities/yandex", headers=auth_header(token))
    assert r.status_code == 200
    assert [i["type"] for i in r.json()] == ["password"]

    lst = await client.get("/api/v1/auth/identities", headers=auth_header(token))
    assert [i["type"] for i in lst.json()] == ["password"]


async def test_unlink_type_not_present_returns_404(client):
    token, _uid = await _oauth_login(client, "yandex", "no-pw-code")
    await client.post(
        "/api/v1/auth/identities/oauth/vk", json={"code": "extra-vk"}, headers=auth_header(token)
    )
    r = await client.delete("/api/v1/auth/identities/password", headers=auth_header(token))
    assert r.status_code == 404
    assert r.json()["detail"] == "IDENTITY_NOT_FOUND"


async def test_unlink_invalid_type_returns_422(client):
    token, _uid = await _oauth_login(client, "yandex", "inv-type-code")
    r = await client.delete("/api/v1/auth/identities/telegram", headers=auth_header(token))
    assert r.status_code == 422


# ── регрессия: обычный вход не сломан ──────────────────────────────────────────────────────
async def test_plain_oauth_login_still_creates_new_user_for_unknown_code(client, db_session):
    from sqlalchemy import func, select

    from app.models.user import User

    before = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    r = await client.post("/api/v1/auth/oauth/yandex", json={"code": "totally-new-code"})
    assert r.status_code == 200
    after = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    assert after == before + 1
