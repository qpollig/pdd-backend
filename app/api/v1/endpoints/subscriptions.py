from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.billing import CancelSubscriptionResponse, SubscriptionOut
from app.schemas.common import ErrorDetail
from app.services import billing_service

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get(
    "/me",
    response_model=SubscriptionOut,
    responses={404: {"model": ErrorDetail, "description": "SUBSCRIPTION_NOT_FOUND — Premium ни разу не покупался"}},
)
async def get_my_subscription(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubscriptionOut:
    """
    Текущая подписка пользователя (статус, дата окончания оплаченного периода,
    флаг автопродления). 404 SUBSCRIPTION_NOT_FOUND — пользователь ни разу не покупал
    Premium (это ожидаемое состояние для Free-пользователя, не ошибка).
    """
    subscription = await billing_service.get_subscription_by_user(db, user.id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SUBSCRIPTION_NOT_FOUND")
    return SubscriptionOut.model_validate(subscription)


@router.post(
    "/cancel",
    response_model=CancelSubscriptionResponse,
    responses={404: {"model": ErrorDetail, "description": "SUBSCRIPTION_NOT_FOUND — Premium ни разу не покупался"}},
)
async def cancel_subscription(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CancelSubscriptionResponse:
    subscription = await billing_service.cancel_auto_renew(db, user)
    return CancelSubscriptionResponse(subscription=SubscriptionOut.model_validate(subscription))
