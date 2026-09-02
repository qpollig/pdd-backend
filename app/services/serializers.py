import uuid

from app.core.config import settings
from app.models.content import Question
from app.models.session import SessionMode
from app.schemas.content import AnswerOut, QuestionOut

# is_correct показывается в режимах "Теория", "Ошибки" и "Избранное" (это режимы повторения/
# самопроверки, не экзамена). В "Экзамене ГИБДД" скрывается до завершения сессии (/finish),
# чтобы исключить читинг.
MODES_WITH_VISIBLE_ANSWER = {SessionMode.theory, SessionMode.errors, SessionMode.favorites}


def build_question_out(
    question: Question,
    mode: SessionMode,
    reveal_answers: bool = False,
    favorite_question_ids: set[uuid.UUID] | None = None,
) -> QuestionOut:
    show_correct = reveal_answers or mode in MODES_WITH_VISIBLE_ANSWER

    # Само изображение хранится в БД (bytea) — в JSON отдаём только путь на эндпоинт,
    # который стримит бинарные данные с нужным Content-Type.
    image_url = f"{settings.API_V1_PREFIX}/questions/{question.id}/image" if question.image_data else None

    return QuestionOut(
        id=question.id,
        order_index=question.order_index,
        text=question.text,
        image_url=image_url,
        explanation=question.explanation,
        is_favorite=(question.id in favorite_question_ids) if favorite_question_ids is not None else False,
        answers=[
            AnswerOut(
                id=a.id,
                order_index=a.order_index,
                text=a.text,
                is_correct=a.is_correct if show_correct else None,
            )
            for a in question.answers
        ],
    )
