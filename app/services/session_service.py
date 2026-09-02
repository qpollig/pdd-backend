import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.content import UserError
from app.models.session import SessionMode, SessionQuestion, SessionStatus, TestSession
from app.models.user import User
from app.services import content_repo
from app.services.lives import deduct_life_on_wrong_answer, ensure_can_start_session
from app.services.serializers import build_question_out
from app.schemas.content import QuestionOut
from app.schemas.session import (
    SessionAnswerRequest,
    SessionAnswerResponse,
    SessionFinishResponse,
    SessionStartRequest,
    SessionStartResponse,
)

# Правильный ответ виден сразу в режимах повторения/самопроверки (Теория, Ошибки, Избранное).
# В "Экзамене ГИБДД" — намеренно нет, чтобы исключить читинг (см. serializers.py).
MODES_WITH_VISIBLE_ANSWER_IN_RESPONSE = (SessionMode.theory, SessionMode.errors, SessionMode.favorites)


async def start_session(db: AsyncSession, user: User, req: SessionStartRequest) -> SessionStartResponse:
    ensure_can_start_session(user)

    if req.mode == SessionMode.theory:
        questions = (
            await content_repo.get_questions_by_ticket(db, req.ticket_id)
            if req.ticket_id
            else await content_repo.get_questions_by_topic(db, req.topic_id)
        )
    elif req.mode == SessionMode.gibdd_exam:
        questions = await content_repo.get_questions_by_ticket(db, req.ticket_id)
    elif req.mode == SessionMode.errors:
        questions = await content_repo.get_user_error_questions(db, user.id)
    elif req.mode == SessionMode.favorites:
        questions = await content_repo.get_user_favorite_questions(db, user.id)
    else:  # pragma: no cover - защищено enum'ом на уровне схемы
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_MODE")

    if not questions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NO_QUESTIONS_FOUND")

    session = TestSession(
        user_id=user.id,
        mode=req.mode,
        ticket_id=req.ticket_id,
        topic_id=req.topic_id,
    )
    db.add(session)
    await db.flush()

    for idx, q in enumerate(questions):
        db.add(SessionQuestion(session_id=session.id, question_id=q.id, order_index=idx, is_extra=False))
    await db.flush()

    # Нужно в любом режиме — например, в "Теории" пользователь может увидеть звёздочку
    # у вопроса, который уже добавил в избранное раньше.
    favorite_ids = await content_repo.get_user_favorite_question_ids(db, user.id)

    return SessionStartResponse(
        session_id=session.id,
        mode=session.mode,
        questions=[build_question_out(q, session.mode, favorite_question_ids=favorite_ids) for q in questions],
        lives_current=user.lives_current,
        lives_max=user.lives_max,
        is_premium=user.is_premium,
    )


async def _get_session_or_404(db: AsyncSession, user: User, session_id: uuid.UUID) -> TestSession:
    result = await db.execute(
        select(TestSession)
        .where(TestSession.id == session_id, TestSession.user_id == user.id)
        .options(selectinload(TestSession.items))
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SESSION_NOT_FOUND")
    if session.status == SessionStatus.finished:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SESSION_ALREADY_FINISHED")
    return session


async def submit_answer(db: AsyncSession, user: User, req: SessionAnswerRequest) -> SessionAnswerResponse:
    session = await _get_session_or_404(db, user, req.session_id)

    item = next((i for i in session.items if i.question_id == req.question_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QUESTION_NOT_IN_SESSION")
    if item.answered:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="QUESTION_ALREADY_ANSWERED")

    question = await content_repo.get_question(db, req.question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QUESTION_NOT_FOUND")

    answer = await content_repo.get_answer(db, req.answer_id)
    if answer is None or answer.question_id != question.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_ANSWER")

    is_correct = answer.is_correct

    item.answered = True
    item.selected_answer_id = answer.id
    item.is_correct = is_correct

    extra_questions_out: list[QuestionOut] = []
    session_finished_forced = False

    if is_correct:
        session.correct_count += 1
        if session.mode == SessionMode.errors:
            # Верный ответ в режиме "Ошибки" -> вопрос считается закрытым, убираем из user_errors
            await db.execute(
                UserError.__table__.delete().where(
                    UserError.user_id == user.id, UserError.question_id == question.id
                )
            )
    else:
        session.errors_count += 1
        deduct_life_on_wrong_answer(user)

        if session.mode == SessionMode.theory:
            # Фиксируем ошибку для последующей работы в режиме "Ошибки"
            existing = await db.execute(
                select(UserError).where(UserError.user_id == user.id, UserError.question_id == question.id)
            )
            if existing.scalar_one_or_none() is None:
                db.add(UserError(user_id=user.id, question_id=question.id))

        if session.mode == SessionMode.gibdd_exam:
            if session.errors_count > settings.EXAM_MAX_ERRORS_ALLOWED:
                # Превышен лимит ошибок — сессия автоматически завершается как непройденная
                session_finished_forced = True
            elif session.extra_questions_added < settings.EXAM_MAX_EXTRA_QUESTIONS:
                remaining_capacity = settings.EXAM_MAX_EXTRA_QUESTIONS - session.extra_questions_added
                to_add = min(settings.EXAM_EXTRA_QUESTIONS_PER_ERROR, remaining_capacity)

                existing_qids = {i.question_id for i in session.items}
                extra_questions = await content_repo.get_extra_exam_questions(
                    db, question.topic_id, existing_qids, to_add
                )

                base_order = len(session.items)
                for offset, extra_q in enumerate(extra_questions):
                    db.add(
                        SessionQuestion(
                            session_id=session.id,
                            question_id=extra_q.id,
                            order_index=base_order + offset,
                            is_extra=True,
                        )
                    )
                session.extra_questions_added += len(extra_questions)
                favorite_ids = await content_repo.get_user_favorite_question_ids(db, user.id)
                extra_questions_out = [
                    build_question_out(q, session.mode, favorite_question_ids=favorite_ids)
                    for q in extra_questions
                ]

    await db.flush()

    return SessionAnswerResponse(
        is_correct=is_correct if session.mode in MODES_WITH_VISIBLE_ANSWER_IN_RESPONSE else None,
        correct_answer_id=(
            next((a.id for a in question.answers if a.is_correct), None)
            if session.mode in MODES_WITH_VISIBLE_ANSWER_IN_RESPONSE
            else None
        ),
        lives_current=user.lives_current,
        extra_questions=extra_questions_out,
        session_finished_forced=session_finished_forced,
    )


async def finish_session(db: AsyncSession, user: User, session_id: uuid.UUID) -> SessionFinishResponse:
    session = await _get_session_or_404(db, user, session_id)

    from datetime import datetime, timezone

    session.status = SessionStatus.finished
    session.finished_at = datetime.now(timezone.utc)
    await db.flush()

    total_questions = len(session.items)
    passed: bool | None = None
    if session.mode == SessionMode.gibdd_exam:
        passed = session.errors_count <= settings.EXAM_MAX_ERRORS_ALLOWED

    return SessionFinishResponse(
        session_id=session.id,
        mode=session.mode,
        status=session.status,
        total_questions=total_questions,
        correct_count=session.correct_count,
        errors_count=session.errors_count,
        passed=passed,
    )
