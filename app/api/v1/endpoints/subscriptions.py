from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.billing import CancelSubscriptionResponse, SubscriptionOut
from app.schemas.common import ErrorDetail
from app.services import billing_service

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("/me", response_model=SubscriptionOut | None)
async def get_my_subscription(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubscriptionOut | None:
    """
    Текущая подписка пользователя (статус, дата окончания оплаченного периода, флаг
    автопродления) либо `null`, если Premium ни разу не покупался.

    Отвечает `200 null` (а не `404`) для Free-пользователя без подписки: это ожидаемое
    состояние, а не ошибка — так в консоли браузера не мигает «Failed to load resource: 404».
    """
    subscription = await billing_service.get_subscription_by_user(db, user.id)
    if subscription is None:
        return None
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
