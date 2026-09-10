"""Существующий OAuth-флоу после миграции 0007: вход идёт через auth_identities.

conftest выставляет OAUTH_ALLOW_MOCK=true и пустые CLIENT_ID/SECRET, поэтому
exchange_code_and_fetch_profile возвращает детерминированный mock-профиль по коду.
"""

from sqlalchemy import func, select

from app.models.auth_identity import AuthIdentity, AuthIdentityType
from app.models.user import User
from tests.conftest import auth_header


async def test_mock_oauth_login_creates_user_and_identity(client, db_session):
    resp = await client.post("/api/v1/auth/oauth/yandex", json={"code": "mock-code-alpha"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["oauth_provider"] == "yandex"

    user_id = body["user"]["id"]
    identities = (
        await db_session.execute(select(AuthIdentity).where(AuthIdentity.user_id == user_id))
    ).scalars().all()
    assert len(identities) == 1
    assert identities[0].type == AuthIdentityType.yandex
    assert identities[0].password_hash is None
    assert identities[0].email_verified_at is not None  # провайдер подтвердил почту


async def test_mock_oauth_login_is_idempotent_for_same_code(client, db_session):
    first = await client.post("/api/v1/auth/oauth/yandex", json={"code": "mock-code-beta"})
    second = await client.post("/api/v1/auth/oauth/yandex", json={"code": "mock-code-beta"})
    assert first.status_code == second.status_code == 200
    assert first.json()["user"]["id"] == second.json()["user"]["id"]

    users = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    identities = (await db_session.execute(select(func.count()).select_from(AuthIdentity))).scalar_one()
    assert users == 1
    assert identities == 1  # второй логин не создал вторую identity


async def test_vk_and_yandex_same_code_are_separate_identities(client, db_session):
    await client.post("/api/v1/auth/oauth/yandex", json={"code": "shared-code"})
    await client.post("/api/v1/auth/oauth/vk", json={"code": "shared-code"})

    by_type = dict(
        (
            await db_session.execute(
                select(AuthIdentity.type, func.count()).group_by(AuthIdentity.type)
            )
        ).all()
    )
    assert by_type == {AuthIdentityType.yandex: 1, AuthIdentityType.vk: 1}
    assert (await db_session.execute(select(func.count()).select_from(User))).scalar_one() == 2


async def test_oauth_token_works_on_protected_endpoint(client):
    token = (
        await client.post("/api/v1/auth/oauth/yandex", json={"code": "mock-code-gamma"})
    ).json()["access_token"]
    me = await client.get("/api/v1/users/me", headers=auth_header(token))
    assert me.status_code == 200
    assert me.json()["oauth_provider"] == "yandex"
