"""POST /api/v1/auth/login."""

from app.core.config import settings
from tests.conftest import auth_header


async def test_login_correct_credentials_returns_200_and_working_token(client, password_user):
    _user, email, password = password_user
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/users/me", headers=auth_header(token))
    assert me.status_code == 200
    assert me.json()["email"] == email


async def test_login_email_is_case_insensitive(client, password_user):
    _user, email, password = password_user
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email.upper(), "password": password}
    )
    assert resp.status_code == 200


async def test_login_wrong_password_returns_401_invalid_credentials(client, password_user):
    _user, email, _password = password_user
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CREDENTIALS"


async def test_login_unknown_email_returns_same_401(client):
    """Несуществующий email — тот же код и тело, что при неверном пароле (не 404):
    не раскрываем, зарегистрирован ли email."""
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever-123"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CREDENTIALS"


async def test_login_user_without_password_identity_cannot_use_password(client, make_user):
    """Строка в users без password-identity (напр. вошёл только через OAuth) не даёт
    входить по паролю — тот же 401."""
    await make_user(email="oauth.only@example.com")
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "oauth.only@example.com", "password": "anything-123"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CREDENTIALS"


async def test_login_wrong_password_and_unknown_email_are_indistinguishable(client, password_user):
    _user, email, _password = password_user
    bad_pw = await client.post("/api/v1/auth/login", json={"email": email, "password": "nope-123456"})
    no_user = await client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope-123456"}
    )
    assert bad_pw.status_code == no_user.status_code == 401
    assert bad_pw.json() == no_user.json()


async def test_login_rate_limited_after_max_attempts(client, password_user):
    _user, email, _password = password_user
    limit = settings.LOGIN_RATE_MAX_ATTEMPTS  # 5

    for i in range(limit):
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        assert r.status_code == 401, f"попытка {i + 1}: {r.status_code}"

    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
    assert r.status_code == 429
    assert r.json()["detail"] == "RATE_LIMITED"

    # даже верный пароль теперь упирается в лимит (ключ = email+IP)
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": _password})
    assert r.status_code == 429


async def test_login_rate_limit_is_per_email(client, make_password_user):
    _u1, email1, pw1 = await make_password_user()
    _u2, email2, pw2 = await make_password_user()
    for _ in range(settings.LOGIN_RATE_MAX_ATTEMPTS):
        await client.post("/api/v1/auth/login", json={"email": email1, "password": "wrong"})
    assert (
        await client.post("/api/v1/auth/login", json={"email": email1, "password": "wrong"})
    ).status_code == 429
    # другой email тем же клиентом — не затронут
    assert (
        await client.post("/api/v1/auth/login", json={"email": email2, "password": pw2})
    ).status_code == 200
