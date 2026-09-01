from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.billing import CancelSubscriptionResponse, SubscriptionOut
from app.services import billing_service

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("/cancel", response_model=CancelSubscriptionResponse)
async def cancel_subscription(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CancelSubscriptionResponse:
    subscription = await billing_service.cancel_auto_renew(db, user)
    return CancelSubscriptionResponse(subscription=SubscriptionOut.model_validate(subscription))
