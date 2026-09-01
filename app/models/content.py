import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Topic(Base):
    """Тематический блок ПДД (напр. 'Дорожные знаки', 'Проезд перекрёстков')."""

    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    questions: Mapped[list["Question"]] = relationship(back_populates="topic")


class Ticket(Base):
    """Один из 40 официальных экзаменационных билетов."""

    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)  # 1..40

    questions: Mapped[list["Question"]] = relationship(back_populates="ticket", order_by="Question.order_index")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False
    )

    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    ticket: Mapped["Ticket | None"] = relationship(back_populates="questions")
    topic: Mapped["Topic"] = relationship(back_populates="questions")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="question", order_by="Answer.order_index", cascade="all, delete-orphan"
    )


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    question: Mapped["Question"] = relationship(back_populates="answers")


class UserError(Base):
    """Вопросы, отвеченные пользователем неверно — используется режимом 'Ошибки'."""

    __tablename__ = "user_errors"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "question_id", name="uq_user_errors_user_question"),)
