import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.billing import Payment, PaymentStatus, Subscription, SubscriptionStatus
from app.models.user import User
from app.services import acquiring

logger = logging.getLogger(__name__)


async def process_recurring_billing() -> None:
    """
    Находит подписки, у которых закончился оплаченный период (paid_until <= now())
    и auto_renew == True, и делает рекуррентное списание 299 РУБ по rebill_id.

    Успех -> paid_until += 30 дней, status = active.
    Ошибка -> is_premium = False, status = cancelled.
    """
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription).where(
                Subscription.paid_until <= now,
                Subscription.auto_renew.is_(True),
                Subscription.status.in_([SubscriptionStatus.trialing, SubscriptionStatus.active]),
            )
        )
        due_subscriptions = list(result.scalars().all())
        logger.info("Recurring billing: %s subscriptions due", len(due_subscriptions))

        for subscription in due_subscriptions:
            await _charge_one_subscription(session, subscription)

        await session.commit()


async def _charge_one_subscription(session, subscription: Subscription) -> None:
    user_result = await session.execute(select(User).where(User.id == subscription.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not subscription.rebill_id:
        subscription.status = SubscriptionStatus.cancelled
        subscription.auto_renew = False
        if user is not None:
            user.is_premium = False
        return

    try:
        result = await acquiring.charge_recurrent(
            rebill_id=subscription.rebill_id,
            amount_rub=subscription.price_rub or settings.SUBSCRIPTION_PRICE_RUB,
            user_id=user.id,
        )
    except acquiring.AcquiringError:
        logger.exception("Recurring charge request failed for subscription %s", subscription.id)
        result = None

    payment = Payment(
        user_id=user.id,
        subscription_id=subscription.id,
        external_payment_id=(result.external_payment_id if result else None),
        amount_rub=subscription.price_rub or settings.SUBSCRIPTION_PRICE_RUB,
        status=PaymentStatus.succeeded if (result and result.success) else PaymentStatus.failed,
        is_recurrent=True,
    )
    session.add(payment)

    if result and result.success:
        subscription.status = SubscriptionStatus.active
        subscription.paid_until = subscription.paid_until + timedelta(days=settings.SUBSCRIPTION_PERIOD_DAYS)
        user.is_premium = True
    else:
        subscription.status = SubscriptionStatus.cancelled
        subscription.auto_renew = False
        user.is_premium = False
