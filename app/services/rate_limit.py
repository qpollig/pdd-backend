"""Простейший in-memory rate limiter (скользящее окно) для MVP.

Ограничения (осознанно, зафиксировано в README):
  * состояние живёт в памяти процесса — при нескольких uvicorn-воркерах у каждого свой счётчик,
    при рестарте счётчики обнуляются;
  * не защищает от распределённой (много процессов/машин) атаки.
Для продакшена под нагрузкой — вынести в Redis (ключи те же). Здесь достаточно для защиты
dev-сервера от брутфорса пароля и email-бомбардировки.
"""

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
_lock = threading.Lock()


def _prune(key: tuple[str, str], now: float, window_seconds: float) -> list[float]:
    fresh = [ts for ts in _buckets[key] if ts > now - window_seconds]
    _buckets[key] = fresh
    return fresh


def hit(scope: str, key: str, *, max_hits: int, window_seconds: float) -> bool:
    """Регистрирует одну попытку. Возвращает True, если лимит НЕ превышен (запрос можно
    продолжать), False — если превышен."""
    bucket_key = (scope, key)
    now = time.time()
    with _lock:
        fresh = _prune(bucket_key, now, window_seconds)
        if len(fresh) >= max_hits:
            return False
        fresh.append(now)
        return True


def enforce(scope: str, key: str, *, max_hits: int, window_seconds: float) -> None:
    """То же, что hit(), но при превышении сразу бросает 429 RATE_LIMITED."""
    if not hit(scope, key, max_hits=max_hits, window_seconds=window_seconds):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="RATE_LIMITED")


def client_ip(request: Request) -> str:
    """IP клиента с учётом обратного прокси (Nginx фронтенда шлёт X-Forwarded-For)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def reset() -> None:
    """Только для тестов/отладки — очистить все счётчики."""
    with _lock:
        _buckets.clear()
