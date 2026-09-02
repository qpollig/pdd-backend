import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.content import Answer, Question, Ticket, Topic, UserError, UserFavorite


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


async def get_user_errors_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(select(func.count()).select_from(UserError).where(UserError.user_id == user_id))
    return result.scalar_one()


async def get_user_favorite_questions(db: AsyncSession, user_id: uuid.UUID) -> list[Question]:
    result = await db.execute(
        select(Question)
        .join(UserFavorite, UserFavorite.question_id == Question.id)
        .where(UserFavorite.user_id == user_id)
        .options(selectinload(Question.answers))
        .order_by(UserFavorite.created_at.desc())
    )
    return list(result.scalars().all())


async def get_user_favorite_question_ids(db: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    result = await db.execute(select(UserFavorite.question_id).where(UserFavorite.user_id == user_id))
    return set(result.scalars().all())


async def get_user_favorites_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(select(func.count()).select_from(UserFavorite).where(UserFavorite.user_id == user_id))
    return result.scalar_one()


async def add_favorite(db: AsyncSession, user_id: uuid.UUID, question_id: uuid.UUID) -> None:
    """Идемпотентно: повторный вызов для уже добавленного вопроса ничего не ломает
    (ON CONFLICT DO NOTHING по уникальной паре user_id+question_id)."""
    stmt = (
        pg_insert(UserFavorite)
        .values(user_id=user_id, question_id=question_id)
        .on_conflict_do_nothing(constraint="uq_user_favorites_user_question")
    )
    await db.execute(stmt)


async def remove_favorite(db: AsyncSession, user_id: uuid.UUID, question_id: uuid.UUID) -> None:
    await db.execute(
        UserFavorite.__table__.delete().where(
            UserFavorite.user_id == user_id, UserFavorite.question_id == question_id
        )
    )


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
