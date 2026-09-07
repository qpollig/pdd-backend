import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.billing import PaymentStatus
from app.models.user import User
from app.schemas.billing import BillingWebhookPayload, CheckoutInitResponse
from app.services import billing_service, user_repo

router = APIRouter(prefix="/billing", tags=["billing"])


def _mock_acquirer_enabled() -> bool:
    """Мок-эквайринг доступен только пока не заданы реальные ключи ЮKassa."""
    return not (settings.ACQUIRER_SHOP_ID and settings.ACQUIRER_SECRET_KEY)


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


@router.get("/mock-pay/{payment_id}", response_class=HTMLResponse, include_in_schema=False)
async def mock_pay_page(payment_id: str, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Заглушка платёжной страницы ЮKassa для локальной разработки. Реальный эквайринг
    показывает свою форму оплаты; здесь — одна кнопка «Оплатить», которая помечает платёж
    успешным и возвращает браузер на BILLING_RETURN_URL (полный аналог return_url ЮKassa)."""
    if not _mock_acquirer_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MOCK_ACQUIRER_DISABLED")

    payment = await billing_service.get_payment_by_external_id(db, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PAYMENT_NOT_FOUND")

    already_paid = payment.status == PaymentStatus.succeeded
    action = f"{settings.API_V1_PREFIX}/billing/mock-pay/{payment_id}/complete"
    body = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>ЮKassa (заглушка)</title>
<style>
 body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f4f4f6;margin:0;
   display:flex;min-height:100vh;align-items:center;justify-content:center}}
 .card{{background:#fff;border-radius:16px;padding:32px 28px;max-width:360px;width:90%;
   box-shadow:0 10px 40px rgba(0,0,0,.08);text-align:center}}
 h1{{font-size:18px;margin:0 0 4px}} p{{color:#6b7280;font-size:14px;margin:4px 0 20px}}
 .amount{{font-size:32px;font-weight:700;margin:8px 0 20px}}
 button{{background:#5b6ee1;color:#fff;border:0;border-radius:10px;padding:12px 20px;font-size:15px;
   font-weight:600;cursor:pointer;width:100%}}
 a{{display:inline-block;margin-top:14px;color:#6b7280;font-size:13px}}
 .note{{margin-top:18px;font-size:12px;color:#9ca3af}}
</style></head><body><div class="card">
 <h1>Оплата подписки</h1>
 <p>Пробный период {settings.TRIAL_PERIOD_DAYS} дня, далее {settings.SUBSCRIPTION_PRICE_RUB} ₽/мес</p>
 <div class="amount">{payment.amount_rub} ₽</div>
 {'<p>Платёж уже подтверждён.</p>' if already_paid else ''}
 <form method="post" action="{action}">
   <button type="submit">{'Вернуться в приложение' if already_paid else 'Оплатить'}</button>
 </form>
 <a href="{settings.BILLING_RETURN_URL}">Отменить и вернуться</a>
 <div class="note">Это тестовая страница-заглушка. Реальное списание не производится.</div>
</div></body></html>"""
    return HTMLResponse(content=body)


@router.post("/mock-pay/{payment_id}/complete", include_in_schema=False)
async def mock_pay_complete(payment_id: str, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """«Подтверждение оплаты» в заглушке: активирует триал/Premium (как это сделал бы вебхук
    ЮKassa) и редиректит браузер на BILLING_RETURN_URL с ?checkout=success."""
    if not _mock_acquirer_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MOCK_ACQUIRER_DISABLED")

    payment = await billing_service.get_payment_by_external_id(db, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PAYMENT_NOT_FOUND")

    user = await user_repo.get_user_by_id(db, payment.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    if payment.status != PaymentStatus.succeeded:
        await billing_service.handle_successful_trial_payment(
            db, user, external_payment_id=payment_id, rebill_id=f"mock-rebill-{payment_id}"
        )

    sep = "&" if "?" in settings.BILLING_RETURN_URL else "?"
    return RedirectResponse(
        url=f"{settings.BILLING_RETURN_URL}{sep}checkout=success",
        status_code=status.HTTP_303_SEE_OTHER,
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
