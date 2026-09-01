"""ticket category + binary image storage

Revision ID: 0002_ticket_category_images
Revises: 0001_initial
Create Date: 2026-09-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0002_ticket_category_images"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    ticket_category_enum = pg.ENUM("A_B", "C_D", name="ticket_category", create_type=False)
    ticket_category_enum.create(bind, checkfirst=True)

    # --- tickets: снимаем unique(number), добавляем category + unique(number, category) ---
    op.drop_constraint("tickets_number_key", "tickets", type_="unique")
    op.add_column(
        "tickets",
        sa.Column("category", ticket_category_enum, nullable=False, server_default="A_B"),
    )
    op.alter_column("tickets", "category", server_default=None)
    op.create_unique_constraint("uq_tickets_number_category", "tickets", ["number", "category"])

    # --- questions: заменяем image_url (строка-ссылка) на бинарное хранение в БД ---
    op.add_column("questions", sa.Column("image_data", sa.LargeBinary(), nullable=True))
    op.add_column("questions", sa.Column("image_content_type", sa.String(length=50), nullable=True))
    op.drop_column("questions", "image_url")


def downgrade() -> None:
    op.add_column("questions", sa.Column("image_url", sa.String(length=1024), nullable=True))
    op.drop_column("questions", "image_content_type")
    op.drop_column("questions", "image_data")

    op.drop_constraint("uq_tickets_number_category", "tickets", type_="unique")
    op.drop_column("tickets", "category")
    op.create_unique_constraint("tickets_number_key", "tickets", ["number"])

    bind = op.get_bind()
    pg.ENUM(name="ticket_category").drop(bind, checkfirst=True)
