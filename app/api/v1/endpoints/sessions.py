from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ErrorDetail
from app.schemas.session import (
    SessionAnswerRequest,
    SessionAnswerResponse,
    SessionFinishRequest,
    SessionFinishResponse,
    SessionStartRequest,
    SessionStartResponse,
)
from app.services import session_service

router = APIRouter(prefix="/tickets/session", tags=["sessions"])


@router.post(
    "/start",
    response_model=SessionStartResponse,
    responses={
        403: {"model": ErrorDetail, "description": "OUT_OF_LIVES — у Free-пользователя закончились жизни"},
        404: {
            "model": ErrorDetail,
            "description": "NO_QUESTIONS_FOUND — по заданным ticket_id/topic_id вопросов не найдено "
            "(или у пользователя пусто в 'Ошибках'/'Избранном')",
        },
    },
)
async def start_session(
    payload: SessionStartRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionStartResponse:
    return await session_service.start_session(db, user, payload)


@router.post(
    "/answer",
    response_model=SessionAnswerResponse,
    responses={
        400: {"model": ErrorDetail, "description": "INVALID_ANSWER — answer_id не относится к этому question_id"},
        404: {
            "model": ErrorDetail,
            "description": "SESSION_NOT_FOUND / QUESTION_NOT_IN_SESSION / QUESTION_NOT_FOUND",
        },
        409: {
            "model": ErrorDetail,
            "description": "SESSION_ALREADY_FINISHED / QUESTION_ALREADY_ANSWERED",
        },
    },
)
async def submit_answer(
    payload: SessionAnswerRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionAnswerResponse:
    return await session_service.submit_answer(db, user, payload)


@router.post(
    "/finish",
    response_model=SessionFinishResponse,
    responses={
        404: {"model": ErrorDetail, "description": "SESSION_NOT_FOUND"},
        409: {"model": ErrorDetail, "description": "SESSION_ALREADY_FINISHED"},
    },
)
async def finish_session(
    payload: SessionFinishRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionFinishResponse:
    return await session_service.finish_session(db, user, payload.session_id)
