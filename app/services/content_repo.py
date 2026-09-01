import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.content import Answer, Question, Ticket, Topic, UserError


async def list_topics(db: AsyncSession) -> list[Topic]:
    result = await db.execute(select(Topic).order_by(Topic.order_index))
    return list(result.scalars().all())


async def list_tickets(db: AsyncSession) -> list[Ticket]:
    result = await db.execute(select(Ticket).order_by(Ticket.number))
    return list(result.scalars().all())


async def get_questions_by_ticket(db: AsyncSession, ticket_id: uuid.UUID) -> list[Question]:
    result = await db.execute(
        select(Question)
        .where(Question.ticket_id == ticket_id)
        .options(selectinload(Question.answers))
        .order_by(Question.order_index)
    )
    return list(result.scalars().all())


async def get_questions_by_topic(db: AsyncSession, topic_id: uuid.UUID) -> list[Question]:
    result = await db.execute(
        select(Question)
        .where(Question.topic_id == topic_id)
        .options(selectinload(Question.answers))
        .order_by(Question.order_index)
    )
    return list(result.scalars().all())


async def get_user_error_questions(db: AsyncSession, user_id: uuid.UUID) -> list[Question]:
    result = await db.execute(
        select(Question)
        .join(UserError, UserError.question_id == Question.id)
        .where(UserError.user_id == user_id)
        .options(selectinload(Question.answers))
        .order_by(UserError.created_at)
    )
    return list(result.scalars().all())


async def get_question(db: AsyncSession, question_id: uuid.UUID) -> Question | None:
    result = await db.execute(
        select(Question).where(Question.id == question_id).options(selectinload(Question.answers))
    )
    return result.scalar_one_or_none()


async def get_answer(db: AsyncSession, answer_id: uuid.UUID) -> Answer | None:
    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    return result.scalar_one_or_none()


async def get_extra_exam_questions(
    db: AsyncSession,
    topic_id: uuid.UUID,
    exclude_question_ids: set[uuid.UUID],
    limit: int,
) -> list[Question]:
    """Доп. вопросы из того же тематического блока, что и вопрос, на котором пользователь ошибся."""
    result = await db.execute(
        select(Question)
        .where(Question.topic_id == topic_id, Question.id.notin_(exclude_question_ids))
        .options(selectinload(Question.answers))
        .order_by(Question.order_index)
        .limit(limit)
    )
    return list(result.scalars().all())
