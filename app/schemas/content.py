import uuid

from pydantic import BaseModel, ConfigDict


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    order_index: int


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int


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
    image_url: str | None
    explanation: str | None
    answers: list[AnswerOut]


class TopicsListResponse(BaseModel):
    topics: list[TopicOut]
    tickets: list[TicketOut]
