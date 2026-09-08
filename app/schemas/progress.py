import enum
import uuid
from datetime import datetime

from pydantic import BaseModel


class TicketProgressStatus(str, enum.Enum):
    not_started = "not_started"  # серый — билет ещё не открывали
    in_progress = "in_progress"  # красный — начат, но не завершён
    passed = "passed"  # зелёный — хотя бы раз завершён без ошибок
    failed = "failed"  # красный — завершался, но с ошибками (и ни разу без)


class TicketProgressOut(BaseModel):
    ticket_id: uuid.UUID
    status: TicketProgressStatus
    attempts: int  # сколько раз билет проходили в режиме theory
    best_correct: int  # лучший результат (верных ответов) среди попыток
    total_questions: int
    last_attempt_at: datetime | None


class TopicProgressOut(BaseModel):
    topic_id: uuid.UUID
    questions_total: int  # всего вопросов в теме (категория A_B)
    questions_passed: int  # на сколько разных вопросов темы хотя бы раз дан верный ответ


class BankProgressOut(BaseModel):
    """Прогресс по всему банку вопросов (для виджета «Прогресс» на дашборде) —
    только верно решённые уникальные вопросы, не все отвеченные."""

    questions_total: int
    questions_passed: int


class ProgressResponse(BaseModel):
    tickets: list[TicketProgressOut]
    topics: list[TopicProgressOut]
    bank: BankProgressOut
