"""Add signals table and feedback columns to ai_recommendations.

Revision ID: c92d88f11a04
Revises: b71e88d022f3
Create Date: 2026-08-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c92d88f11a04"
down_revision = "b71e88d022f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create signals table
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=50), nullable=False),
        sa.Column("signal_type", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=50), server_default="INTERNAL_TASKS", nullable=False),
        sa.Column(
            "provenance", sa.String(length=50), server_default="SYSTEM_DERIVED", nullable=False
        ),
        sa.Column("importance", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("urgency", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signals_user_id", "signals", ["user_id"], unique=False)
    op.create_index("ix_signals_domain", "signals", ["domain"], unique=False)
    op.create_index("ix_signals_signal_type", "signals", ["signal_type"], unique=False)
    op.create_index("ix_signals_timestamp", "signals", ["timestamp"], unique=False)
    op.create_index("ix_signals_expires_at", "signals", ["expires_at"], unique=False)
    op.create_index("ix_signals_is_active", "signals", ["is_active"], unique=False)
    op.create_index(
        "ix_signals_user_domain_active", "signals", ["user_id", "domain", "is_active"], unique=False
    )

    # 2. Add columns to ai_recommendations
    with op.batch_alter_table("ai_recommendations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "decision_type",
                sa.String(length=30),
                server_default="SHOULD_DO",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("opportunity_cost", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("evidence", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("context_snapshot", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("feedback", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("feedback_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("feedback_at", sa.DateTime(), nullable=True))
        batch_op.create_index(
            "ix_ai_recommendations_decision_type", ["decision_type"], unique=False
        )
        batch_op.create_index("ix_ai_recommendations_feedback", ["feedback"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ai_recommendations") as batch_op:
        batch_op.drop_index("ix_ai_recommendations_feedback")
        batch_op.drop_index("ix_ai_recommendations_decision_type")
        batch_op.drop_column("feedback_at")
        batch_op.drop_column("feedback_notes")
        batch_op.drop_column("feedback")
        batch_op.drop_column("context_snapshot")
        batch_op.drop_column("evidence")
        batch_op.drop_column("opportunity_cost")
        batch_op.drop_column("decision_type")

    op.drop_index("ix_signals_user_domain_active", table_name="signals")
    op.drop_index("ix_signals_is_active", table_name="signals")
    op.drop_index("ix_signals_expires_at", table_name="signals")
    op.drop_index("ix_signals_timestamp", table_name="signals")
    op.drop_index("ix_signals_signal_type", table_name="signals")
    op.drop_index("ix_signals_domain", table_name="signals")
    op.drop_index("ix_signals_user_id", table_name="signals")
    op.drop_table("signals")
