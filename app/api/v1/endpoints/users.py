from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.user import UserOut
from app.services import user_repo

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    """
    Полный профиль текущего пользователя: жизни, Premium-статус, счётчики "Ошибок"
    и "Избранного". Нужен фронтенду, чтобы обновить эти данные без повторного логина
    и без обязательного старта тестовой сессии (например, чтобы просто показать
    бейджи "5 ошибок" / "12 в избранном" на главном экране).
    """
    return await user_repo.build_user_out(db, user)
