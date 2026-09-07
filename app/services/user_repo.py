import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import OAuthProvider, User
from app.schemas.user import UserOut
from app.services import content_repo


def _next_lives_reset_at(now: datetime | None = None) -> datetime:
    """Ближайшее наступление LIVES_RESET_HOUR_UTC:00 (по умолчанию 00:00 UTC) — момент,
    когда джоба reset_free_users_lives вернёт жизни до lives_max."""
    now = now or datetime.now(timezone.utc)
    reset_today = datetime.combine(now.date(), time(hour=settings.LIVES_RESET_HOUR_UTC), tzinfo=timezone.utc)
    return reset_today if reset_today > now else reset_today + timedelta(days=1)


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_oauth(db: AsyncSession, provider: OAuthProvider, oauth_id: str) -> User | None:
    result = await db.execute(
        select(User).where(User.oauth_provider == provider, User.oauth_id == oauth_id)
    )
    return result.scalar_one_or_none()


async def create_or_update_oauth_user(
    db: AsyncSession,
    provider: OAuthProvider,
    oauth_id: str,
    name: str | None,
    email: str | None,
    avatar_url: str | None,
) -> User:
    user = await get_user_by_oauth(db, provider, oauth_id)
    if user is None:
        user = User(
            oauth_provider=provider,
            oauth_id=oauth_id,
            name=name,
            email=email,
            avatar_url=avatar_url,
        )
        db.add(user)
    else:
        user.name = name or user.name
        user.email = email or user.email
        user.avatar_url = avatar_url or user.avatar_url

    await db.flush()
    return user


async def build_user_out(db: AsyncSession, user: User) -> UserOut:
    """UserOut дополняет ORM-объект User посчитанными на лету полями (errors_count,
    favorites_count), которых нет в самой таблице users — поэтому обычный
    model_validate(user) их не заполнит."""
    errors_count = await content_repo.get_user_errors_count(db, user.id)
    favorites_count = await content_repo.get_user_favorites_count(db, user.id)
    # Premium жизни не расходует — «регенерация» относится только к Free; для Premium
    # это поле не имеет смысла, отдаём null.
    lives_regen_at = None if user.is_premium else _next_lives_reset_at()
    return UserOut(
        id=user.id,
        oauth_provider=user.oauth_provider,
        name=user.name,
        avatar_url=user.avatar_url,
        email=user.email,
        lives_current=user.lives_current,
        lives_max=user.lives_max,
        is_premium=user.is_premium,
        errors_count=errors_count,
        favorites_count=favorites_count,
        lives_reset_at=user.lives_reset_at,
        lives_regen_at=lives_regen_at,
    )
