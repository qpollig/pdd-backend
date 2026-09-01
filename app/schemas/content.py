import uuid

from pydantic import BaseModel, ConfigDict

from app.models.content import TicketCategory


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    order_index: int


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    category: TicketCategory


class AnswerOut(BaseModel):
    """is_correct заполняется только для режимов theory/errors — см. build_answer_out()."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_index: int
    text: str
    is_correct: bool | None = None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_index: int
    text: str
    image_url: str | None  # относительный путь на наш эндпоинт /questions/{id}/image, не внешняя ссылка
    explanation: str | None
    answers: list[AnswerOut]


class TopicsListResponse(BaseModel):
    topics: list[TopicOut]
    tickets: list[TicketOut]

