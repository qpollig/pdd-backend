import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import User  # noqa: F401 — используется в аннотации Mapped["User"]


class AuthIdentityType(str, enum.Enum):
    """Способ входа. В Фазе 1 у пользователя ровно одна identity; Фаза 2 разрешит несколько
    (password + oauth одновременно), поэтому это отдельная таблица, а не колонки в users."""

    password = "password"
    yandex = "yandex"
    vk = "vk"


class AuthIdentity(Base):
    """Один способ входа = одна строка. Заменяет прежние users.oauth_provider/oauth_id."""

    __tablename__ = "auth_identities"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    type: Mapped[AuthIdentityType] = mapped_column(
        Enum(AuthIdentityType, name="auth_identity_type"), nullable=False
    )
    # email — для type='password'; oauth_id провайдера — для 'yandex' / 'vk'.
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    # Заполнен только для type='password'. bcrypt-хеш (см. app/services/passwords.py).
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Когда email подтверждён. Для oauth — сразу (провайдер уже подтвердил владение почтой).
    # Для password в Фазе 1 остаётся NULL: верификация email отложена в Фазу 2 (см. auth.py).
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(backref="auth_identities")

    __table_args__ = (
        # Один и тот же email / oauth_id не может быть привязан дважды (в т.ч. к разным users).
        UniqueConstraint("type", "identifier", name="uq_auth_identities_type_identifier"),
    )


class PasswordResetToken(Base):
    """Одноразовый токен сброса пароля. В БД хранится ТОЛЬКО sha256-хеш токена — сам токен
    существует лишь в письме, поэтому утечка БД не даёт сбросить чужой пароль."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("auth_identities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # sha256 hex
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    identity: Mapped["AuthIdentity"] = relationship()
