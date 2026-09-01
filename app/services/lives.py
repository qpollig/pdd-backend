from fastapi import HTTPException, status

from app.models.user import User


def ensure_can_start_session(user: User) -> None:
    """Free-пользователь без жизней не может начать новую сессию. Premium — без ограничений."""
    if user.is_premium:
        return
    if user.lives_current <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OUT_OF_LIVES",
        )


def deduct_life_on_wrong_answer(user: User) -> None:
    """Списывает 1 жизнь у Free-пользователя при неверном ответе. Premium — не трогаем."""
    if user.is_premium:
        return
    if user.lives_current > 0:
        user.lives_current -= 1
