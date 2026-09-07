"""lives default 5 -> 10 (ТЗ v1.5, раздел 4.7)

Revision ID: 0005_lives_default_10
Revises: 0004_question_video_url
Create Date: 2026-09-03

ТЗ v1.5, раздел 4.7: users.lives_current и users.lives_max имеют default 10
(модель «+1 жизнь через 24 ч» + верхняя граница 10). В 0001 колонки были заведены
с server_default="5" — приводим к 10 и подтягиваем уже существующие строки,
где лимит остался старым дефолтным.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0005_lives_default_10"
down_revision: Union[str, None] = "0004_question_video_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "lives_current", server_default="10")
    op.alter_column("users", "lives_max", server_default="10")
    # Существующие пользователи с ещё старым дефолтным лимитом 5 -> 10.
    # Тех, у кого lives_max уже кастомный (акции и т.п.), не трогаем.
    op.execute("UPDATE users SET lives_max = 10 WHERE lives_max = 5")
    op.execute("UPDATE users SET lives_current = 10 WHERE lives_current = 5 AND lives_max = 10")


def downgrade() -> None:
    op.alter_column("users", "lives_current", server_default="5")
    op.alter_column("users", "lives_max", server_default="5")
