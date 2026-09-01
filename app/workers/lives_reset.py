import logging
from datetime import datetime, timezone

from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)


async def reset_free_users_lives() -> None:
    """
    Ежесуточный сброс жизней (00:00 UTC) до lives_max для всех пользователей.
    Premium-пользователей не трогаем (у них lives не расходуются), но обновление
    безопасно и для них — просто выравнивает lives_current = lives_max.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(User).values(lives_current=User.lives_max, lives_reset_at=datetime.now(timezone.utc))
        )
        await session.commit()
        logger.info("Lives reset job completed, rows_matched=%s", result.rowcount)
