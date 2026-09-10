"""Единая точка импорта всех моделей — используется Alembic для autogenerate."""

from app.models.auth_identity import AuthIdentity, PasswordResetToken  # noqa: F401
from app.models.billing import Payment, Subscription  # noqa: F401
from app.models.content import Answer, Question, Ticket, Topic, UserError, UserFavorite  # noqa: F401
from app.models.session import SessionQuestion, TestSession  # noqa: F401
from app.models.user import User  # noqa: F401
