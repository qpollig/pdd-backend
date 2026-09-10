import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_identity import AuthIdentity, AuthIdentityType
from app.models.user import OAuthProvider, User
from app.schemas.user import UserOut
from app.services import auth_identity_repo, content_repo


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_or_update_oauth_user(
    db: AsyncSession,
    provider: OAuthProvider,
    oauth_id: str,
    name: str | None,
    email: str | None,
    avatar_url: str | None,
) -> User:
    """Вход через OAuth. Внешний контракт не изменился, но способ входа теперь хранится в
    auth_identities, а не в колонках users.oauth_provider/oauth_id."""
    identity_type = AuthIdentityType(provider.value)
    identity = await auth_identity_repo.get_identity(db, identity_type, oauth_id)

    if identity is not None:
        user = await get_user_by_id(db, identity.user_id)
        assert user is not None  # FK ON DELETE CASCADE гарантирует консистентность
        user.name = name or user.name
        user.email = email or user.email
        user.avatar_url = avatar_url or user.avatar_url
        await db.flush()
        return user

    user = User(name=name, email=email, avatar_url=avatar_url)
    db.add(user)
    await db.flush()
    db.add(
        AuthIdentity(
            user_id=user.id,
            type=identity_type,
            identifier=oauth_id,
            # OAuth-провайдер уже подтвердил владение почтой.
            email_verified_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    return user


async def create_password_user(
    db: AsyncSession, email: str, name: str, password_hash: str
) -> tuple[User, AuthIdentity]:
    """Регистрация по email+паролю: users + auth_identities(type='password')."""
    user = User(name=name, email=auth_identity_repo.normalize_email(email))
    db.add(user)
    await db.flush()
    identity = AuthIdentity(
        user_id=user.id,
        type=AuthIdentityType.password,
        identifier=auth_identity_repo.normalize_email(email),
        password_hash=password_hash,
        # Фаза 1: верификация email опциональна (см. auth.py) — остаётся NULL.
        email_verified_at=None,
    )
    db.add(identity)
    await db.flush()
    return user, identity


async def build_user_out(db: AsyncSession, user: User) -> UserOut:
    """UserOut дополняет ORM-объект User посчитанными на лету полями (errors_count,
    favorites_count) и oauth_provider, которых нет в самой таблице users."""
    errors_count = await content_repo.get_user_errors_count(db, user.id)
    favorites_count = await content_repo.get_user_favorites_count(db, user.id)
    oauth_identity = await auth_identity_repo.oauth_identity_for_user(db, user.id)
    # Обратная совместимость: фронтенд ждёт oauth_provider в UserOut. Для oauth-пользователей
    # значение то же, что раньше; для password-only — null (на фронте это поле никто не читает).
    oauth_provider = OAuthProvider(oauth_identity.type.value) if oauth_identity else None
    return UserOut(
        id=user.id,
        oauth_provider=oauth_provider,
        name=user.name,
        avatar_url=user.avatar_url,
        email=user.email,
        lives_current=user.lives_current,
        lives_max=user.lives_max,
        is_premium=user.is_premium,
        errors_count=errors_count,
        favorites_count=favorites_count,
        lives_reset_at=user.lives_reset_at,
        # ТЗ §4.7: момент начисления следующей +1 жизни (null — жизни на максимуме / Premium).
        lives_regen_at=user.lives_regen_at,
    )
