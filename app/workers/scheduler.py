import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.workers.billing_recurring import process_recurring_billing
from app.workers.lives_reset import reset_free_users_lives

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


def setup_scheduler() -> AsyncIOScheduler:
    # Сброс жизней ежедневно в 00:00 UTC
    scheduler.add_job(
        reset_free_users_lives,
        trigger=CronTrigger(hour=settings.LIVES_RESET_HOUR_UTC, minute=0),
        id="reset_free_users_lives",
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

    logger.info("Scheduler configured: lives_reset@%02d:00 UTC, billing every %sm",
                settings.LIVES_RESET_HOUR_UTC, settings.BILLING_WORKER_INTERVAL_MINUTES)
    return scheduler
