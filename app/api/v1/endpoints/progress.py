from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.progress import ProgressResponse
from app.services import progress_service

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("", response_model=ProgressResponse)
async def get_progress(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProgressResponse:
    """Прогресс текущего пользователя, посчитанный на бэкенде (не сбрасывается при перезагрузке):

    - `tickets[]` — статус каждого билета категории A_B (`not_started` / `in_progress` / `passed` /
      `failed`) для раскраски сетки билетов: зелёный = хотя бы раз пройден без ошибок,
      красный = начат и не завершён либо завершён с ошибками.
    - `topics[]` — по каждой теме: сколько разных вопросов уже решено верно из общего числа.
    - `bank` — то же по всему банку вопросов (для виджета «Прогресс»): только верно решённые
      уникальные вопросы, а не все отвеченные.
    """
    return await progress_service.build_progress(db, user.id)
