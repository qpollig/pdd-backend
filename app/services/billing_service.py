import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.billing import Payment, PaymentStatus, Subscription, SubscriptionStatus
from app.models.user import User
from app.services import acquiring


async def init_checkout(db: AsyncSession, user: User) -> tuple[str, str]:
    payment_id, confirmation_url = await acquiring.init_trial_payment(user.id)

    db.add(
        Payment(
            user_id=user.id,
            external_payment_id=payment_id,
            amount_rub=settings.TRIAL_PRICE_RUB,
            status=PaymentStatus.pending,
            is_recurrent=False,
        )
    )
    await db.flush()
    return payment_id, confirmation_url


async def get_subscription_by_user(db: AsyncSession, user_id: uuid.UUID) -> Subscription | None:
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    return result.scalar_one_or_none()


async def get_payment_by_external_id(db: AsyncSession, external_payment_id: str) -> Payment | None:
    result = await db.execute(select(Payment).where(Payment.external_payment_id == external_payment_id))
    return result.scalar_one_or_none()


async def handle_successful_trial_payment(
    db: AsyncSession, user: User, external_payment_id: str, rebill_id: str | None
) -> None:
    """Первый платёж (1 РУБ) прошёл успешно: активируем триал и Premium, сохраняем rebill_id."""
    payment = await get_payment_by_external_id(db, external_payment_id)
    if payment is not None:
        payment.status = PaymentStatus.succeeded

    now = datetime.now(timezone.utc)
    trial_end = now + timedelta(days=settings.TRIAL_PERIOD_DAYS)

    subscription = await get_subscription_by_user(db, user.id)
    if subscription is None:
        subscription = Subscription(
            user_id=user.id,
            status=SubscriptionStatus.trialing,
            rebill_id=rebill_id,
            auto_renew=True,
            paid_until=trial_end,
            price_rub=settings.SUBSCRIPTION_PRICE_RUB,
        )
        db.add(subscription)
    else:
        subscription.status = SubscriptionStatus.trialing
        subscription.rebill_id = rebill_id or subscription.rebill_id
        subscription.auto_renew = True
        subscription.paid_until = trial_end

    user.is_premium = True
    await db.flush()

    if payment is not None:
        payment.subscription_id = subscription.id
        await db.flush()


async def cancel_auto_renew(db: AsyncSession, user: User) -> Subscription:
    subscription = await get_subscription_by_user(db, user.id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SUBSCRIPTION_NOT_FOUND")

    subscription.auto_renew = False
    await db.flush()
    return subscription
