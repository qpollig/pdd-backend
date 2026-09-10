"""email+password auth: auth_identities + password_reset_tokens, users.oauth_* вынесены

Revision ID: 0007_email_password_auth
Revises: 0006_lives_regen_and_exam_passed
Create Date: 2026-09-10

Что делает upgrade:
  1. enum auth_identity_type ('password' | 'yandex' | 'vk');
  2. таблица auth_identities — один способ входа = одна строка (прицел на Фазу 2, где у
     пользователя их несколько);
  3. таблица password_reset_tokens — одноразовые токены сброса (в БД только sha256-хеш);
  4. DATA-миграция: для каждой строки users с oauth_provider/oauth_id создаётся
     auth_identities(type=oauth_provider, identifier=oauth_id, created_at=users.created_at);
  5. со users снимается UNIQUE(oauth_provider, oauth_id) и удаляются сами колонки
     oauth_provider/oauth_id (users.email остаётся — это профильное поле);
  6. осиротевший enum-тип oauth_provider удаляется.

downgrade — не заглушка: разворачивает oauth-данные обратно в users.oauth_provider/oauth_id.
Данные, существовавшие ДО апгрейда (oauth-пользователи), восстанавливаются один-в-один.
Пользователи, заведённые ПОСЛЕ апгрейда только по паролю, в старую схему не вписываются
(там oauth_* были NOT NULL) — у них поля останутся NULL, а NOT NULL вернётся только если
таких пользователей нет (т.е. при откате до появления первой парольной регистрации).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0007_email_password_auth"
down_revision: Union[str, None] = "0006_lives_regen_and_exam_passed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    auth_identity_type = pg.ENUM(
        "password", "yandex", "vk", name="auth_identity_type", create_type=False
    )
    auth_identity_type.create(bind, checkfirst=True)

    op.create_table(
        "auth_identities",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", auth_identity_type, nullable=False),
        sa.Column("identifier", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("type", "identifier", name="uq_auth_identities_type_identifier"),
    )
    op.create_index("ix_auth_identities_user_id", "auth_identities", ["user_id"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column(
            "identity_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("auth_identities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_password_reset_tokens_identity_id", "password_reset_tokens", ["identity_id"])

    # 4. Data-миграция существующих oauth-пользователей.
    op.execute(
        """
        INSERT INTO auth_identities (id, user_id, type, identifier, email_verified_at, created_at)
        SELECT uuid_generate_v4(),
               u.id,
               u.oauth_provider::text::auth_identity_type,
               u.oauth_id,
               u.created_at,          -- oauth-провайдер уже подтвердил владение почтой
               u.created_at
        FROM users u
        WHERE u.oauth_provider IS NOT NULL AND u.oauth_id IS NOT NULL
        """
    )

    # 5. Снять уникальное ограничение и удалить колонки.
    op.drop_constraint("uq_users_provider_oauth_id", "users", type_="unique")
    op.drop_column("users", "oauth_id")
    op.drop_column("users", "oauth_provider")

    # 6. Тип oauth_provider больше не используется ни одной колонкой.
    pg.ENUM(name="oauth_provider").drop(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()

    # 1. Пересоздать enum-тип до колонки, которая на него ссылается.
    oauth_provider_enum = pg.ENUM("yandex", "vk", name="oauth_provider", create_type=False)
    oauth_provider_enum.create(bind, checkfirst=True)

    # 2. Вернуть колонки (пока nullable — заполним данными ниже).
    op.add_column("users", sa.Column("oauth_provider", oauth_provider_enum, nullable=True))
    op.add_column("users", sa.Column("oauth_id", sa.String(128), nullable=True))

    # 3. Развернуть oauth-identity обратно в колонки users. DISTINCT ON — на случай, если во
    #    Фазе 2 у пользователя окажется несколько oauth-identity: берём самую раннюю.
    op.execute(
        """
        UPDATE users u
        SET oauth_provider = ai.type::text::oauth_provider,
            oauth_id       = ai.identifier
        FROM (
            SELECT DISTINCT ON (user_id) user_id, type, identifier
            FROM auth_identities
            WHERE type IN ('yandex', 'vk')
            ORDER BY user_id, created_at
        ) ai
        WHERE ai.user_id = u.id
        """
    )

    # 4. Вернуть уникальное ограничение (NULL-значения в PG не конфликтуют между собой,
    #    поэтому password-only пользователи с NULL в oauth_* ему не мешают).
    op.create_unique_constraint(
        "uq_users_provider_oauth_id", "users", ["oauth_provider", "oauth_id"]
    )

    # 5. Если ни одного пользователя без oauth (т.е. откат до первой парольной регистрации) —
    #    вернуть NOT NULL, как было в исходной схеме. Иначе оставить nullable (потеря данных
    #    недопустима).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM users WHERE oauth_provider IS NULL OR oauth_id IS NULL) THEN
                ALTER TABLE users ALTER COLUMN oauth_provider SET NOT NULL;
                ALTER TABLE users ALTER COLUMN oauth_id SET NOT NULL;
            END IF;
        END $$
        """
    )

    # 6. Убрать новые таблицы и enum.
    op.drop_index("ix_password_reset_tokens_identity_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("ix_auth_identities_user_id", table_name="auth_identities")
    op.drop_table("auth_identities")
    pg.ENUM(name="auth_identity_type").drop(bind, checkfirst=True)
