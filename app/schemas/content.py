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
    """is_correct заполняется только в режимах theory/errors/favorites — см. build_question_out()."""

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
    is_favorite: bool = False
    answers: list[AnswerOut]


class FavoritesListResponse(BaseModel):
    questions: list[QuestionOut]


class FavoriteToggleResponse(BaseModel):
    question_id: uuid.UUID
    is_favorite: bool


class TopicsListResponse(BaseModel):
    topics: list[TopicOut]
    tickets: list[TicketOut]

