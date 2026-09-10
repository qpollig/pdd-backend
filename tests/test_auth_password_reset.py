"""POST /api/v1/auth/password/forgot и POST /api/v1/auth/password/reset."""

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.models.auth_identity import PasswordResetToken
from app.services.auth_identity_repo import hash_reset_token
from tests.conftest import token_from_email_body


# ── forgot ──────────────────────────────────────────────────────────────────────────────────
async def test_forgot_known_and_unknown_email_return_identical_200(client, password_user):
    _user, email, _pw = password_user
    known = await client.post("/api/v1/auth/password/forgot", json={"email": email})
    unknown = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "does-not-exist@example.com"}
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()  # тело идентично, не только код


async def test_forgot_creates_exactly_one_token_row_hashed(client, db_session, password_user, mail_outbox):
    _user, email, _pw = password_user
    await client.post("/api/v1/auth/password/forgot", json={"email": email})

    rows = (await db_session.execute(select(PasswordResetToken))).scalars().all()
    assert len(rows) == 1

    raw = token_from_email_body(mail_outbox[0].body_text)
    assert rows[0].token_hash != raw                      # сырой токен в БД не лежит
    assert rows[0].token_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert rows[0].used_at is None
    assert rows[0].expires_at > datetime.now(timezone.utc)


async def test_forgot_unknown_email_creates_no_token(client, db_session):
    await client.post("/api/v1/auth/password/forgot", json={"email": "ghost@example.com"})
    count = (await db_session.execute(select(func.count()).select_from(PasswordResetToken))).scalar_one()
    assert count == 0


async def test_forgot_second_request_invalidates_previous_token(client, db_session, password_user, mail_outbox):
    _user, email, _pw = password_user
    await client.post("/api/v1/auth/password/forgot", json={"email": email})
    await client.post("/api/v1/auth/password/forgot", json={"email": email})

    rows = (
        await db_session.execute(select(PasswordResetToken).order_by(PasswordResetToken.created_at))
    ).scalars().all()
    assert len(rows) == 2
    assert rows[0].used_at is not None   # старый погашен
    assert rows[1].used_at is None       # активен только последний


async def test_forgot_rate_limited_per_email(client, password_user):
    _user, email, _pw = password_user
    for _ in range(settings.PASSWORD_FORGOT_RATE_MAX_PER_EMAIL):  # 3
        assert (
            await client.post("/api/v1/auth/password/forgot", json={"email": email})
        ).status_code == 200
    r = await client.post("/api/v1/auth/password/forgot", json={"email": email})
    assert r.status_code == 429
    assert r.json()["detail"] == "RATE_LIMITED"


async def test_forgot_rate_limited_per_ip_across_different_emails(client):
    """Один клиент бомбит разные адреса — упирается в лимит по IP."""
    for i in range(settings.PASSWORD_FORGOT_RATE_MAX_PER_IP):  # 10
        r = await client.post("/api/v1/auth/password/forgot", json={"email": f"victim{i}@example.com"})
        assert r.status_code == 200
    r = await client.post("/api/v1/auth/password/forgot", json={"email": "victim-final@example.com"})
    assert r.status_code == 429


# ── reset ───────────────────────────────────────────────────────────────────────────────────
async def _request_reset_token(client, mail_outbox, email: str) -> str:
    await client.post("/api/v1/auth/password/forgot", json={"email": email})
    return token_from_email_body(mail_outbox[-1].body_text)


async def test_reset_changes_password_old_stops_working_new_works(client, password_user, mail_outbox):
    _user, email, old_pw = password_user
    token = await _request_reset_token(client, mail_outbox, email)
    new_pw = "brand-new-password-9"

    resp = await client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": new_pw})
    assert resp.status_code == 200

    assert (
        await client.post("/api/v1/auth/login", json={"email": email, "password": old_pw})
    ).status_code == 401
    assert (
        await client.post("/api/v1/auth/login", json={"email": email, "password": new_pw})
    ).status_code == 200


async def test_reset_token_is_single_use(client, password_user, mail_outbox):
    _user, email, _old = password_user
    token = await _request_reset_token(client, mail_outbox, email)

    first = await client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "new-pass-11"})
    assert first.status_code == 200
    second = await client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "new-pass-22"})
    assert second.status_code == 400
    assert second.json()["detail"] == "INVALID_OR_EXPIRED_TOKEN"


async def test_reset_with_garbage_token_returns_400(client):
    resp = await client.post(
        "/api/v1/auth/password/reset", json={"token": "totally-made-up-token", "new_password": "whatever-12"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "INVALID_OR_EXPIRED_TOKEN"


async def test_reset_with_expired_token_returns_400(client, db_session, password_user):
    """Истечение проверяем, создавая токен напрямую в БД с прошедшим expires_at."""
    _user, email, _pw = password_user
    from app.services.auth_identity_repo import get_password_identity_by_email

    identity = await get_password_identity_by_email(db_session, email)
    raw = "expired-raw-token-value"
    db_session.add(
        PasswordResetToken(
            identity_id=identity.id,
            token_hash=hash_reset_token(raw),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    await db_session.flush()

    resp = await client.post("/api/v1/auth/password/reset", json={"token": raw, "new_password": "new-pass-33"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "INVALID_OR_EXPIRED_TOKEN"


async def test_reset_rejects_too_short_new_password(client, password_user, mail_outbox):
    _user, email, _old = password_user
    token = await _request_reset_token(client, mail_outbox, email)
    resp = await client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "short"})
    assert resp.status_code == 422
