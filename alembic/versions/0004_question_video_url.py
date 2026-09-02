"""question video_url (CDN link for 3D video breakdown)

Revision ID: 0004_question_video_url
Revises: 0003_favorites
Create Date: 2026-09-02

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004_question_video_url"
down_revision: Union[str, None] = "0003_favorites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 3D-видеоразбор — ключевое УТП продукта. Видео не хранится в БД/на диске приложения
    # (в отличие от image_data), а лежит в отдельном Object Storage и раздаётся через CDN —
    # здесь хранится только полная ссылка на файл.
    op.add_column("questions", sa.Column("video_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "video_url")
