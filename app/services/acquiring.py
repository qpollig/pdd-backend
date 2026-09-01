import uuid
from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass
class ChargeResult:
    success: bool
    external_payment_id: str
    raw_response: dict


class AcquiringError(Exception):
    pass


async def init_trial_payment(user_id: uuid.UUID) -> tuple[str, str]:
    """
    Инициализация первого платежа (1 РУБ, сохранение карты по rebill).
    Возвращает (payment_id, confirmation_url).

    Реальная интеграция с ЮKassa/Т-Банк подключается здесь; ниже — заготовка под ЮKassa API
    (save_payment_method=true для получения rebill-токена при последующих списаниях).
    """
    idempotence_key = str(uuid.uuid4())
    payload = {
        "amount": {"value": f"{settings.TRIAL_PRICE_RUB:.2f}", "currency": "RUB"},
        "capture": True,
        "save_payment_method": True,
        "confirmation": {"type": "redirect", "return_url": settings.OAUTH_REDIRECT_URI},
        "description": f"Пробный период {settings.TRIAL_PERIOD_DAYS} дня — {settings.TRIAL_PRICE_RUB} ₽",
        "metadata": {"user_id": str(user_id), "kind": "trial"},
    }

    if not settings.ACQUIRER_SHOP_ID or not settings.ACQUIRER_SECRET_KEY:
        # Локальная разработка без реальных ключей эквайринга — возвращаем заглушку.
        fake_payment_id = f"local-{idempotence_key}"
        return fake_payment_id, f"https://pay.example.com/mock/{fake_payment_id}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.yookassa.ru/v3/payments",
            json=payload,
            auth=(settings.ACQUIRER_SHOP_ID, settings.ACQUIRER_SECRET_KEY),
            headers={"Idempotence-Key": idempotence_key},
        )
        if resp.status_code not in (200, 201):
            raise AcquiringError(f"Checkout init failed: {resp.text}")
        data = resp.json()

    return data["id"], data["confirmation"]["confirmation_url"]


async def charge_recurrent(rebill_id: str, amount_rub: int, user_id: uuid.UUID) -> ChargeResult:
    """Рекуррентное списание по сохранённому rebill_id (без участия пользователя)."""
    idempotence_key = str(uuid.uuid4())
    payload = {
        "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
        "capture": True,
        "payment_method_id": rebill_id,
        "description": f"Продление подписки — {amount_rub} ₽",
        "metadata": {"user_id": str(user_id), "kind": "recurrent"},
    }

    if not settings.ACQUIRER_SHOP_ID or not settings.ACQUIRER_SECRET_KEY:
        return ChargeResult(success=True, external_payment_id=f"local-{idempotence_key}", raw_response={})

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.yookassa.ru/v3/payments",
            json=payload,
            auth=(settings.ACQUIRER_SHOP_ID, settings.ACQUIRER_SECRET_KEY),
            headers={"Idempotence-Key": idempotence_key},
        )
        data = resp.json()
        success = resp.status_code in (200, 201) and data.get("status") == "succeeded"
        return ChargeResult(success=success, external_payment_id=data.get("id", ""), raw_response=data)
