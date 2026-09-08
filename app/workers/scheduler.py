import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.workers.billing_recurring import process_recurring_billing
from app.workers.lives_reset import regen_free_users_lives

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


def setup_scheduler() -> AsyncIOScheduler:
    # Восстановление жизней (ТЗ §4.7) — подстраховка к ленивому регену, раз в час.
    scheduler.add_job(
        regen_free_users_lives,
        trigger=IntervalTrigger(hours=1),
        id="regen_free_users_lives",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Рекуррентный биллинг — раз в BILLING_WORKER_INTERVAL_MINUTES минут
    scheduler.add_job(
        process_recurring_billing,
        trigger=IntervalTrigger(minutes=settings.BILLING_WORKER_INTERVAL_MINUTES),
        id="process_recurring_billing",
        replace_existing=True,
        misfire_grace_time=600,
    )

    logger.info("Scheduler configured: lives_regen every 60m (+%sh interval), billing every %sm",
                settings.LIVES_REGEN_HOURS, settings.BILLING_WORKER_INTERVAL_MINUTES)
    return scheduler
