"""initial schema - phase 1 MVP

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-31

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    oauth_provider_enum = pg.ENUM("yandex", "vk", name="oauth_provider")
    session_mode_enum = pg.ENUM("theory", "gibdd_exam", "errors", name="session_mode")
    session_status_enum = pg.ENUM("in_progress", "finished", name="session_status")
    subscription_status_enum = pg.ENUM(
        "trialing", "active", "cancelled", "past_due", name="subscription_status"
    )
    payment_status_enum = pg.ENUM("pending", "succeeded", "failed", name="payment_status")

    bind = op.get_bind()
    oauth_provider_enum.create(bind, checkfirst=True)
    session_mode_enum.create(bind, checkfirst=True)
    session_status_enum.create(bind, checkfirst=True)
    subscription_status_enum.create(bind, checkfirst=True)
    payment_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("oauth_provider", oauth_provider_enum, nullable=False),
        sa.Column("oauth_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(1024), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("lives_current", sa.Integer, nullable=False, server_default="5"),
        sa.Column("lives_max", sa.Integer, nullable=False, server_default="5"),
        sa.Column("lives_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_premium", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("oauth_provider", "oauth_id", name="uq_users_provider_oauth_id"),
    )

    op.create_table(
        "topics",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "tickets",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("number", sa.Integer, nullable=False, unique=True),
    )

    op.create_table(
        "questions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", pg.UUID(as_uuid=True), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("topic_id", pg.UUID(as_uuid=True), sa.ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("image_url", sa.String(1024), nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
    )
    op.create_index("ix_questions_ticket_id", "questions", ["ticket_id"])
    op.create_index("ix_questions_topic_id", "questions", ["topic_id"])

    op.create_table(
        "answers",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_id", pg.UUID(as_uuid=True), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_answers_question_id", "answers", ["question_id"])

    op.create_table(
        "user_errors",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", pg.UUID(as_uuid=True), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "question_id", name="uq_user_errors_user_question"),
    )

    op.create_table(
        "test_sessions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", session_mode_enum, nullable=False),
        sa.Column("ticket_id", pg.UUID(as_uuid=True), sa.ForeignKey("tickets.id"), nullable=True),
        sa.Column("topic_id", pg.UUID(as_uuid=True), sa.ForeignKey("topics.id"), nullable=True),
        sa.Column("status", session_status_enum, nullable=False, server_default="in_progress"),
        sa.Column("errors_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("extra_questions_added", sa.Integer, nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_test_sessions_user_id", "test_sessions", ["user_id"])

    op.create_table(
        "session_questions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", pg.UUID(as_uuid=True), sa.ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", pg.UUID(as_uuid=True), sa.ForeignKey("questions.id"), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_extra", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("answered", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("selected_answer_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("is_correct", sa.Boolean, nullable=True),
        sa.UniqueConstraint("session_id", "question_id", name="uq_session_question"),
    )
    op.create_index("ix_session_questions_session_id", "session_questions", ["session_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", subscription_status_enum, nullable=False, server_default="trialing"),
        sa.Column("rebill_id", sa.String(255), nullable=True),
        sa.Column("auto_renew", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("paid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_rub", sa.Integer, nullable=False, server_default="299"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "payments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", pg.UUID(as_uuid=True), sa.ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_payment_id", sa.String(255), nullable=True, unique=True),
        sa.Column("amount_rub", sa.Integer, nullable=False),
        sa.Column("status", payment_status_enum, nullable=False, server_default="pending"),
        sa.Column("is_recurrent", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("subscriptions")
    op.drop_table("session_questions")
    op.drop_table("test_sessions")
    op.drop_table("user_errors")
    op.drop_table("answers")
    op.drop_table("questions")
    op.drop_table("tickets")
    op.drop_table("topics")
    op.drop_table("users")

    bind = op.get_bind()
    pg.ENUM(name="payment_status").drop(bind, checkfirst=True)
    pg.ENUM(name="subscription_status").drop(bind, checkfirst=True)
    pg.ENUM(name="session_status").drop(bind, checkfirst=True)
    pg.ENUM(name="session_mode").drop(bind, checkfirst=True)
    pg.ENUM(name="oauth_provider").drop(bind, checkfirst=True)
