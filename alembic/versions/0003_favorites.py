"""favorites feature

Revision ID: 0003_favorites
Revises: 0002_ticket_category_images
Create Date: 2026-09-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0003_favorites"
down_revision: Union[str, None] = "0002_ticket_category_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Новое значение enum'а session_mode для режима "Избранное".
    # ВАЖНО: ALTER TYPE ... ADD VALUE нельзя использовать в той же транзакции, где значение
    # уже применяется — но здесь мы его только добавляем, не используем, так что это безопасно
    # в рамках одной транзакционной миграции (Postgres 12+).
    op.execute("ALTER TYPE session_mode ADD VALUE IF NOT EXISTS 'favorites'")

    op.create_table(
        "user_favorites",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "question_id", pg.UUID(as_uuid=True), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "question_id", name="uq_user_favorites_user_question"),
    )
    op.create_index("ix_user_favorites_user_id", "user_favorites", ["user_id"])


def downgrade() -> None:
    op.drop_table("user_favorites")
    # Postgres не поддерживает удаление одного значения enum — потребовалось бы пересоздание
    # типа целиком. Для downgrade оставляем значение 'favorites' в enum (безвредно: колонка
    # session_mode просто не будет использовать его после отката кода приложения).
