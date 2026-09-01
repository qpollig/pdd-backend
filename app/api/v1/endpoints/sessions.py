from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
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


@router.post("/start", response_model=SessionStartResponse)
async def start_session(
    payload: SessionStartRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionStartResponse:
    return await session_service.start_session(db, user, payload)


@router.post("/answer", response_model=SessionAnswerResponse)
async def submit_answer(
    payload: SessionAnswerRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionAnswerResponse:
    return await session_service.submit_answer(db, user, payload)


@router.post("/finish", response_model=SessionFinishResponse)
async def finish_session(
    payload: SessionFinishRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionFinishResponse:
    return await session_service.finish_session(db, user, payload.session_id)
