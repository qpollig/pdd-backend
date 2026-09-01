from app.core.config import settings
from app.models.content import Question
from app.models.session import SessionMode
from app.schemas.content import AnswerOut, QuestionOut

# is_correct показывается только в режимах "Теория" и "Ошибки".
# В "Экзамене ГИБДД" скрывается до завершения сессии (/finish), чтобы исключить читинг.
MODES_WITH_VISIBLE_ANSWER = {SessionMode.theory, SessionMode.errors}


def build_question_out(question: Question, mode: SessionMode, reveal_answers: bool = False) -> QuestionOut:
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
