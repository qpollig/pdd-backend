import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import OAuthProvider, User


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
