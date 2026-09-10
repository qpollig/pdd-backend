import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.database import Base


class OAuthProvider(str, enum.Enum):
    """Провайдеры OAuth. Значения совпадают с соответствующими членами AuthIdentityType —
    сам способ входа теперь хранится в таблице auth_identities, а этот enum остаётся для
    валидации path-параметра /auth/oauth/{provider}."""

    yandex = "yandex"
    vk = "vk"


class User(Base):
    """Профиль пользователя. Способы входа (password / yandex / vk) вынесены в auth_identities
    (миграция 0007) — с прицелом на Фазу 2, где у одного пользователя их будет несколько.
    users.email остаётся как профильное поле (не идентификатор входа)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

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
