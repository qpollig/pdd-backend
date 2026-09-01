import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.billing import SubscriptionStatus


class CheckoutInitResponse(BaseModel):
    payment_id: str
    confirmation_url: str
    amount_rub: int
    description: str


class BillingWebhookPayload(BaseModel):
    """Упрощённая нормализованная форма вебхука эквайринга (ЮKassa/Т-Банк)."""

    event: str  # напр. "payment.succeeded" / "payment.failed"
    payment_id: str
    status: str
    amount_rub: int
    rebill_id: str | None = None
    metadata: dict = {}


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: SubscriptionStatus
    auto_renew: bool
    paid_until: datetime
    price_rub: int


class CancelSubscriptionResponse(BaseModel):
    subscription: SubscriptionOut
    message: str = "Автопродление отключено. Premium активен до конца оплаченного периода."
