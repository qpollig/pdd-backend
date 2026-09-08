from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.core.config import settings
from app.models.user import User


def _regen_interval() -> timedelta:
    return timedelta(hours=settings.LIVES_REGEN_HOURS)


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def apply_lives_regen(user: User, now: datetime | None = None) -> None:
    """ТЗ v1.5 §4.7: «+1 жизнь через LIVES_REGEN_HOURS часов с момента, когда жизни опустились
    ниже максимума». Ленивое начисление — вызывается при каждом обращении к пользователю
    (см. get_current_user) и периодической джобой-подстраховкой.

    Инвариант: `lives_regen_at` — это момент начисления СЛЕДУЮЩЕЙ +1 жизни; NULL, когда жизни
    на максимуме. Если пользователь долго не заходил, начисляем сразу за все прошедшие интервалы.
    """
    now = now or datetime.now(timezone.utc)

    if user.is_premium:
        # Premium жизни не расходует — таймер не нужен.
        user.lives_regen_at = None
        return

    if user.lives_current >= user.lives_max:
        user.lives_regen_at = None
        return

    if user.lives_regen_at is None:
        # Жизни ниже максимума, а таймер не запущен (например, выставлены вручную) — запускаем.
        user.lives_regen_at = now + _regen_interval()
        return

    regen_at = _as_utc(user.lives_regen_at)
    if now < regen_at:
        return

    interval = _regen_interval()
    # Сколько раз «настал» момент начисления к текущему времени.
    ticks = 1 + int((now - regen_at) // interval)
    new_current = min(user.lives_max, user.lives_current + ticks)
    user.lives_current = new_current
    user.lives_reset_at = now

    if new_current >= user.lives_max:
        user.lives_regen_at = None
    else:
        user.lives_regen_at = regen_at + interval * ticks


def ensure_can_start_session(user: User) -> None:
    """Free-пользователь без жизней не может начать новую сессию. Premium — без ограничений.
    Восстановление жизней (§4.7) уже применено в get_current_user."""
    if user.is_premium:
        return
    if user.lives_current <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OUT_OF_LIVES",
        )


def deduct_life_on_wrong_answer(user: User) -> None:
    """Списывает 1 жизнь у Free-пользователя при неверном ответе. Premium — не трогаем.
    При падении ниже максимума запускает 24-часовой таймер восстановления, если он ещё не идёт."""
    if user.is_premium:
        return
    if user.lives_current > 0:
        user.lives_current -= 1
    if user.lives_current < user.lives_max and user.lives_regen_at is None:
        user.lives_regen_at = datetime.now(timezone.utc) + _regen_interval()
