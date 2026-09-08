import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.database import Base


class OAuthProvider(str, enum.Enum):
    yandex = "yandex"
    vk = "vk"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # OAuth identity
    oauth_provider: Mapped[OAuthProvider] = mapped_column(Enum(OAuthProvider, name="oauth_provider"), nullable=False)
    oauth_id: Mapped[str] = mapped_column(String(128), nullable=False)

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Freemium gameplay state
    lives_current: Mapped[int] = mapped_column(Integer, nullable=False, default=settings.DEFAULT_LIVES_MAX)
    lives_max: Mapped[int] = mapped_column(Integer, nullable=False, default=settings.DEFAULT_LIVES_MAX)
    # Когда жизни последний раз начислялись джобой/ленивым регеном (для наблюдаемости).
    lives_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ТЗ §4.7: момент начисления следующей +1 жизни. NULL — жизни на максимуме, таймер не идёт.
    lives_regen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Premium status (denormalized flag kept in sync with subscriptions)
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("oauth_provider", "oauth_id", name="uq_users_provider_oauth_id"),)
