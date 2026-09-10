import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.auth_identity import AuthIdentity, AuthIdentityType, PasswordResetToken


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def get_identity(
    db: AsyncSession, identity_type: AuthIdentityType, identifier: str
) -> AuthIdentity | None:
    result = await db.execute(
        select(AuthIdentity).where(
            AuthIdentity.type == identity_type, AuthIdentity.identifier == identifier
        )
    )
    return result.scalar_one_or_none()


async def get_password_identity_by_email(db: AsyncSession, email: str) -> AuthIdentity | None:
    return await get_identity(db, AuthIdentityType.password, normalize_email(email))


async def create_password_reset_token(db: AsyncSession, identity: AuthIdentity) -> str:
    """Создаёт одноразовый токен сброса. Возвращает СЫРОЙ токен (для письма); в БД кладём
    только его sha256-хеш. Прежние неиспользованные токены этой identity гасим."""
    await db.execute(
        PasswordResetToken.__table__.update()
        .where(
            PasswordResetToken.identity_id == identity.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(timezone.utc))
    )

    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            identity_id=identity.id,
            token_hash=hash_reset_token(raw_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_TTL_MINUTES),
        )
    )
    await db.flush()
    return raw_token


async def consume_password_reset_token(db: AsyncSession, raw_token: str) -> AuthIdentity | None:
    """Проверяет токен и сразу помечает использованным (одноразовость). Возвращает identity
    при успехе, None — если токен неизвестен / истёк / уже использован."""
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_reset_token(raw_token)
        )
    )
    token = result.scalar_one_or_none()
    if token is None or token.used_at is not None:
        return None

    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return None

    token.used_at = datetime.now(timezone.utc)

    identity = await db.get(AuthIdentity, token.identity_id)
    await db.flush()
    return identity


async def oauth_identity_for_user(db: AsyncSession, user_id: uuid.UUID) -> AuthIdentity | None:
    """Первая (по created_at) oauth-identity пользователя — для обратной совместимости
    UserOut.oauth_provider."""
    result = await db.execute(
        select(AuthIdentity)
        .where(
            AuthIdentity.user_id == user_id,
            AuthIdentity.type.in_([AuthIdentityType.yandex, AuthIdentityType.vk]),
        )
        .order_by(AuthIdentity.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


# ── Связывание способов входа ────────────────────────────────────────────────────────────────
async def list_identities_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[AuthIdentity]:
    result = await db.execute(
        select(AuthIdentity)
        .where(AuthIdentity.user_id == user_id)
        .order_by(AuthIdentity.created_at)
        # populate_existing: только что созданная identity получает актуальный server-default
        # created_at из БД, а не None из сессии.
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def password_identity_for_user(db: AsyncSession, user_id: uuid.UUID) -> AuthIdentity | None:
    return await db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.user_id == user_id, AuthIdentity.type == AuthIdentityType.password
        )
    )


async def create_oauth_identity(
    db: AsyncSession, user_id: uuid.UUID, identity_type: AuthIdentityType, oauth_id: str
) -> AuthIdentity:
    identity = AuthIdentity(
        user_id=user_id,
        type=identity_type,
        identifier=oauth_id,
        # OAuth-провайдер уже подтвердил владение почтой.
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(identity)
    await db.flush()
    return identity


async def create_password_identity(
    db: AsyncSession, user_id: uuid.UUID, email: str, password_hash: str
) -> AuthIdentity:
    identity = AuthIdentity(
        user_id=user_id,
        type=AuthIdentityType.password,
        identifier=normalize_email(email),
        password_hash=password_hash,
        # Фаза 1: верификация email опциональна (см. auth.py) — остаётся NULL.
        email_verified_at=None,
    )
    db.add(identity)
    await db.flush()
    return identity
