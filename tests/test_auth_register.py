"""POST /api/v1/auth/register."""

from sqlalchemy import func, select

from app.models.auth_identity import AuthIdentity, AuthIdentityType
from tests.conftest import auth_header


async def test_register_success_returns_token_response(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "new.user@example.com", "password": "valid-password-1", "name": "New User"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # тот же контракт, что у OAuth-логина
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "new.user@example.com"
    assert body["user"]["name"] == "New User"
    assert body["user"]["oauth_provider"] is None  # вход по паролю


async def test_register_persists_user_and_password_identity(client, db_session):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "persisted@example.com", "password": "valid-password-1", "name": "P"},
    )
    identity = (
        await db_session.execute(
            select(AuthIdentity).where(AuthIdentity.identifier == "persisted@example.com")
        )
    ).scalar_one()
    assert identity.type == AuthIdentityType.password
    assert identity.password_hash and identity.password_hash != "valid-password-1"
    assert identity.email_verified_at is None  # верификация опциональна в Фазе 1


async def test_register_token_works_on_protected_endpoint(client):
    token = (
        await client.post(
            "/api/v1/auth/register",
            json={"email": "me@example.com", "password": "valid-password-1", "name": "Me"},
        )
    ).json()["access_token"]

    me = await client.get("/api/v1/users/me", headers=auth_header(token))
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "me@example.com"


async def test_register_duplicate_email_returns_409(client):
    payload = {"email": "dup@example.com", "password": "valid-password-1", "name": "Dup"}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 200
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "EMAIL_ALREADY_REGISTERED"


async def test_register_duplicate_email_case_insensitive_returns_409(client, db_session):
    assert (
        await client.post(
            "/api/v1/auth/register",
            json={"email": "Case.User@Example.Com", "password": "valid-password-1", "name": "A"},
        )
    ).status_code == 200
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "CASE.USER@EXAMPLE.COM", "password": "another-valid-1", "name": "B"},
    )
    assert resp.status_code == 409
    # и в БД по-прежнему одна запись
    count = (
        await db_session.execute(
            select(func.count()).select_from(AuthIdentity).where(AuthIdentity.identifier == "case.user@example.com")
        )
    ).scalar_one()
    assert count == 1


async def test_register_invalid_email_returns_422(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "valid-password-1", "name": "X"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "VALIDATION_ERROR"


async def test_register_password_too_short_returns_422(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "short@example.com", "password": "short", "name": "X"},
    )
    assert resp.status_code == 422


async def test_register_password_too_long_returns_422(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "long@example.com", "password": "x" * 73, "name": "X"},
    )
    assert resp.status_code == 422


async def test_register_empty_name_returns_422(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "noname@example.com", "password": "valid-password-1", "name": ""},
    )
    assert resp.status_code == 422
