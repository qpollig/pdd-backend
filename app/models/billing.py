import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SubscriptionStatus(str, enum.Enum):
    trialing = "trialing"
    active = "active"
    cancelled = "cancelled"
    past_due = "past_due"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"), nullable=False, default=SubscriptionStatus.trialing
    )

    # Токен карты для рекуррентных списаний, выданный эквайрингом
    rebill_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    paid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    price_rub: Mapped[int] = mapped_column(Integer, nullable=False, default=299)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    payments: Mapped[list["Payment"]] = relationship(back_populates="subscription")


class Payment(Base):
    """Лог всех попыток списания (триал, рекуррентные, ошибки) — для аудита и вебхуков."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )

    external_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    amount_rub: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), nullable=False, default=PaymentStatus.pending
    )
    is_recurrent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscription: Mapped["Subscription | None"] = relationship(back_populates="payments")
