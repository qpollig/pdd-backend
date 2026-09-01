import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SessionMode(str, enum.Enum):
    theory = "theory"
    gibdd_exam = "gibdd_exam"
    errors = "errors"


class SessionStatus(str, enum.Enum):
    in_progress = "in_progress"
    finished = "finished"


class TestSession(Base):
    """Одна сессия прохождения (билета / темы / ошибок / экзамена)."""

    __tablename__ = "test_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    mode: Mapped[SessionMode] = mapped_column(Enum(SessionMode, name="session_mode"), nullable=False)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tickets.id"), nullable=True)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("topics.id"), nullable=True)

    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status"), nullable=False, default=SessionStatus.in_progress
    )

    errors_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_questions_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["SessionQuestion"]] = relationship(
        back_populates="session", order_by="SessionQuestion.order_index", cascade="all, delete-orphan"
    )


class SessionQuestion(Base):
    """Конкретный вопрос внутри сессии (в т.ч. доп. вопросы, добавленные при ошибке в экзамене)."""

    __tablename__ = "session_questions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)

    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_extra: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    answered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selected_answer_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    session: Mapped["TestSession"] = relationship(back_populates="items")

    __table_args__ = (UniqueConstraint("session_id", "question_id", name="uq_session_question"),)
