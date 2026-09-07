import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.session import SessionMode
from app.models.user import User
from app.schemas.common import ErrorDetail
from app.schemas.content import FavoriteToggleResponse, FavoritesListResponse
from app.services import content_repo
from app.services.serializers import build_question_out

router = APIRouter(prefix="/questions", tags=["content"])


@router.get(
    "/{question_id}/image",
    responses={404: {"model": ErrorDetail, "description": "IMAGE_NOT_FOUND — вопрос без картинки или не существует"}},
)
async def get_question_image(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    # Без Bearer-авторизации намеренно: картинка вопроса не является секретом (доступ к самому
    # вопросу уже проверен на уровне сессии), а обычный <img src="..."> не может передать
    # заголовок Authorization. Публичный URL к тому же ведёт себя так же, как будущая CDN-ссылка —
    # чтобы переехать на CDN, достаточно поменять формирование image_url в serializers.py,
    # фронтенд менять не придётся.
    question = await content_repo.get_question(db, question_id)
    if question is None or not question.image_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IMAGE_NOT_FOUND")

    return Response(
        content=question.image_data,
        media_type=question.image_content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/favorites", response_model=FavoritesListResponse)
async def list_favorites(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FavoritesListResponse:
    questions = await content_repo.get_user_favorite_questions(db, user.id)
    favorite_ids = {q.id for q in questions}
    return FavoritesListResponse(
        questions=[
            build_question_out(q, mode=SessionMode.favorites, favorite_question_ids=favorite_ids)
            for q in questions
        ]
    )


@router.post(
    "/{question_id}/favorite",
    response_model=FavoriteToggleResponse,
    responses={404: {"model": ErrorDetail, "description": "QUESTION_NOT_FOUND"}},
)
async def add_to_favorites(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FavoriteToggleResponse:
    question = await content_repo.get_question(db, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QUESTION_NOT_FOUND")

    await content_repo.add_favorite(db, user.id, question_id)
    return FavoriteToggleResponse(question_id=question_id, is_favorite=True)


@router.delete("/{question_id}/favorite", response_model=FavoriteToggleResponse)
async def remove_from_favorites(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FavoriteToggleResponse:
    await content_repo.remove_favorite(db, user.id, question_id)
    return FavoriteToggleResponse(question_id=question_id, is_favorite=False)
