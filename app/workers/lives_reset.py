import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services.lives import apply_lives_regen

logger = logging.getLogger(__name__)


async def regen_free_users_lives() -> None:
    """Подстраховка к ленивому восстановлению жизней (ТЗ v1.5 §4.7).

    Ленивый реген в get_current_user покрывает активных пользователей; эта джоба догоняет
    тех, кто давно не заходил, чтобы `lives_current` в БД не «отставал» от реальной модели.
    Идемпотентна: применяет ту же apply_lives_regen, что и запросы.
    """
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(
                User.is_premium.is_(False),
                User.lives_current < User.lives_max,
                User.lives_regen_at.is_not(None),
                User.lives_regen_at <= now,
            )
        )
        users = list(result.scalars().all())
        for user in users:
            apply_lives_regen(user, now)
        await session.commit()
        logger.info("Lives regen job: %s user(s) topped up", len(users))
