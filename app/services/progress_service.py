import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Question, Ticket
from app.models.session import SessionMode, SessionQuestion, SessionStatus, TestSession
from app.schemas.progress import (
    BankProgressOut,
    ProgressResponse,
    TicketProgressOut,
    TicketProgressStatus,
    TopicProgressOut,
)
from app.services.content_repo import ACTIVE_TICKET_CATEGORIES


async def _ticket_question_totals(db: AsyncSession) -> dict[uuid.UUID, int]:
    result = await db.execute(
        select(Question.ticket_id, func.count(Question.id))
        .join(Ticket, Ticket.id == Question.ticket_id)
        .where(Ticket.category.in_(ACTIVE_TICKET_CATEGORIES))
        .group_by(Question.ticket_id)
    )
    return {tid: cnt for tid, cnt in result.all()}


async def _topic_question_totals(db: AsyncSession) -> dict[uuid.UUID, int]:
    result = await db.execute(
        select(Question.topic_id, func.count(Question.id))
        .join(Ticket, Ticket.id == Question.ticket_id)
        .where(Ticket.category.in_(ACTIVE_TICKET_CATEGORIES))
        .group_by(Question.topic_id)
    )
    return {tid: cnt for tid, cnt in result.all()}


async def _distinct_correct_by_topic(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Сколько разных вопросов темы пользователь хотя бы раз решил верно (любой режим, A_B)."""
    result = await db.execute(
        select(Question.topic_id, func.count(func.distinct(SessionQuestion.question_id)))
        .select_from(SessionQuestion)
        .join(TestSession, TestSession.id == SessionQuestion.session_id)
        .join(Question, Question.id == SessionQuestion.question_id)
        .join(Ticket, Ticket.id == Question.ticket_id)
        .where(
            TestSession.user_id == user_id,
            SessionQuestion.is_correct.is_(True),
            Ticket.category.in_(ACTIVE_TICKET_CATEGORIES),
        )
        .group_by(Question.topic_id)
    )
    return {tid: cnt for tid, cnt in result.all()}


async def _theory_sessions_by_ticket(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[uuid.UUID, list[TestSession]]:
    result = await db.execute(
        select(TestSession)
        .join(Ticket, Ticket.id == TestSession.ticket_id)
        .where(
            TestSession.user_id == user_id,
            TestSession.mode == SessionMode.theory,
            TestSession.ticket_id.is_not(None),
            Ticket.category.in_(ACTIVE_TICKET_CATEGORIES),
        )
    )
    by_ticket: dict[uuid.UUID, list[TestSession]] = {}
    for s in result.scalars().all():
        by_ticket.setdefault(s.ticket_id, []).append(s)
    return by_ticket


def _ticket_status(sessions: list[TestSession]) -> TicketProgressStatus:
    if not sessions:
        return TicketProgressStatus.not_started
    finished = [s for s in sessions if s.status == SessionStatus.finished]
    if any(s.errors_count == 0 for s in finished):
        return TicketProgressStatus.passed  # хотя бы раз пройден чисто → зелёный навсегда
    if any(s.status == SessionStatus.in_progress for s in sessions):
        return TicketProgressStatus.in_progress  # начат, не завершён → красный
    return TicketProgressStatus.failed  # завершался только с ошибками → красный


async def build_progress(db: AsyncSession, user_id: uuid.UUID) -> ProgressResponse:
    ticket_totals = await _ticket_question_totals(db)
    topic_totals = await _topic_question_totals(db)
    correct_by_topic = await _distinct_correct_by_topic(db, user_id)
    sessions_by_ticket = await _theory_sessions_by_ticket(db, user_id)

    tickets: list[TicketProgressOut] = []
    for ticket_id, total in ticket_totals.items():
        sessions = sessions_by_ticket.get(ticket_id, [])
        stamps = [s.finished_at or s.started_at for s in sessions if (s.finished_at or s.started_at)]
        tickets.append(
            TicketProgressOut(
                ticket_id=ticket_id,
                status=_ticket_status(sessions),
                attempts=len(sessions),
                best_correct=max((s.correct_count for s in sessions), default=0),
                total_questions=total,
                last_attempt_at=max(stamps) if stamps else None,
            )
        )

    topics = [
        TopicProgressOut(
            topic_id=topic_id,
            questions_total=total,
            questions_passed=min(correct_by_topic.get(topic_id, 0), total),
        )
        for topic_id, total in topic_totals.items()
    ]

    bank_total = sum(topic_totals.values())
    bank_passed = min(sum(correct_by_topic.values()), bank_total)

    return ProgressResponse(
        tickets=tickets,
        topics=topics,
        bank=BankProgressOut(questions_total=bank_total, questions_passed=bank_passed),
    )
