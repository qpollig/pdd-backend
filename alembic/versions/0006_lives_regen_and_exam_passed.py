"""lives regen model (ТЗ v1.5 §4.7) + explicit exam_passed

Revision ID: 0006_lives_regen_and_exam_passed
Revises: 0005_lives_default_10
Create Date: 2026-09-07

1. users.lives_regen_at — момент, когда пользователю будет начислена следующая +1 жизнь
   (модель ТЗ §4.7: «+1 жизнь через 24 ч с момента, когда жизни опустились ниже максимума»).
   NULL — жизни на максимуме, таймер не идёт. Заменяет прежний ежесуточный сброс в 00:00 UTC.
2. test_sessions.exam_passed — явный вердикт по «Экзамену ГИБДД». Проставляется в submit_answer
   (ошибка в доп. вопросе / превышение лимита ошибок → False) и в finish_session. NULL — экзамен
   ещё не завершён либо это не экзамен. Нужен, чтобы форсированное завершение считалось «не сдал»
   даже когда errors_count формально <= лимита.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0006_lives_regen_and_exam_passed"
down_revision: Union[str, None] = "0005_lives_default_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("lives_regen_at", sa.DateTime(timezone=True), nullable=True),
    )
    # У кого сейчас жизни ниже максимума — запускаем таймер восстановления от «сейчас».
    op.execute(
        "UPDATE users SET lives_regen_at = now() + interval '24 hours' "
        "WHERE lives_current < lives_max AND is_premium = false"
    )
    op.add_column(
        "test_sessions",
        sa.Column("exam_passed", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("test_sessions", "exam_passed")
    op.drop_column("users", "lives_regen_at")
