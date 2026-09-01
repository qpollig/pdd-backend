import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.billing import BillingWebhookPayload, CheckoutInitResponse
from app.services import billing_service, user_repo

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout/init", response_model=CheckoutInitResponse)
async def checkout_init(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CheckoutInitResponse:
    payment_id, confirmation_url = await billing_service.init_checkout(db, user)
    return CheckoutInitResponse(
        payment_id=payment_id,
        confirmation_url=confirmation_url,
        amount_rub=settings.TRIAL_PRICE_RUB,
        description=f"Пробный период {settings.TRIAL_PERIOD_DAYS} дня за {settings.TRIAL_PRICE_RUB} ₽",
    )


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def billing_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Принимает вебхук эквайринга (ЮKassa/Т-Банк).

    ВАЖНО: перед продакшн-релизом здесь обязательна проверка подписи/источника запроса
    (IP allowlist эквайринга или HMAC-подпись — в зависимости от провайдера), иначе
    любой внешний вызов сможет выдать Premium без реальной оплаты.
    """
    raw = await request.json()
    payload = _normalize_webhook_payload(raw)

    if payload.status != "succeeded":
        # Платёж не прошёл — просто подтверждаем получение, ничего не активируем.
        return {"ok": True}

    user_id = raw.get("object", {}).get("metadata", {}).get("user_id") or raw.get("metadata", {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MISSING_USER_ID_IN_METADATA")

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_USER_ID") from exc

    user = await user_repo.get_user_by_id(db, user_uuid)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    await billing_service.handle_successful_trial_payment(
        db, user, external_payment_id=payload.payment_id, rebill_id=payload.rebill_id
    )
    return {"ok": True}


def _normalize_webhook_payload(raw: dict) -> BillingWebhookPayload:
    """Приводит формат вебхука ЮKassa/Т-Банк к внутренней нормализованной схеме."""
    obj = raw.get("object", raw)
    amount = obj.get("amount", {})
    payment_method = obj.get("payment_method", {})
    return BillingWebhookPayload(
        event=raw.get("event", ""),
        payment_id=obj.get("id", ""),
        status=obj.get("status", ""),
        amount_rub=int(float(amount.get("value", 0))),
        rebill_id=payment_method.get("id") if payment_method.get("saved") else None,
        metadata=obj.get("metadata", {}),
    )
