import uuid

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.session import SessionMode, SessionStatus
from app.schemas.content import QuestionOut


class SessionStartRequest(BaseModel):
    mode: SessionMode
    ticket_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def check_target(self) -> "SessionStartRequest":
        if self.mode in (SessionMode.theory,) and not self.ticket_id and not self.topic_id:
            raise ValueError("ticket_id или topic_id обязателен для режима theory")
        # gibdd_exam: ticket_id не обязателен — если фронт его не передал, backend сам
        #   выбирает случайный билет активной категории (реальный экзамен ГИБДД —
        #   это случайный билет из 20 вопросов).
        # errors / favorites: ни ticket_id, ни topic_id не требуются — вопросы берутся
        #   из user_errors / user_favorites.
        return self


class SessionStartResponse(BaseModel):
    session_id: uuid.UUID
    mode: SessionMode
    questions: list[QuestionOut]
    lives_current: int
    lives_max: int
    is_premium: bool


class SessionAnswerRequest(BaseModel):
    session_id: uuid.UUID
    question_id: uuid.UUID
    answer_id: uuid.UUID


class SessionAnswerResponse(BaseModel):
    # is_correct скрыт (None) в gibdd_exam до /finish
    is_correct: bool | None
    correct_answer_id: uuid.UUID | None = None
    lives_current: int
    extra_questions: list[QuestionOut] = []
    session_finished_forced: bool = False  # True если исчерпан лимит ошибок в экзамене


class SessionFinishRequest(BaseModel):
    session_id: uuid.UUID


class SessionFinishResponse(BaseModel):
    session_id: uuid.UUID
    mode: SessionMode
    status: SessionStatus
    total_questions: int
    correct_count: int
    errors_count: int
    passed: bool | None = None  # применимо для gibdd_exam
