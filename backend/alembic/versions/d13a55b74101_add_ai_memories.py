"""Add ai_memories table for conversational memory and persistent user context.

Revision ID: d13a55b74101
Revises: c92d88f11a04
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d13a55b74101"
down_revision = "c92d88f11a04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_memories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False, server_default="GENERAL"),
        sa.Column("key", sa.String(length=120), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.9"),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="CONVERSATION_EXTRACTED"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_memories_user_id", "ai_memories", ["user_id"], unique=False)
    op.create_index("ix_ai_memories_conversation_id", "ai_memories", ["conversation_id"], unique=False)
    op.create_index("ix_ai_memories_category", "ai_memories", ["category"], unique=False)
    op.create_index("ix_ai_memories_key", "ai_memories", ["key"], unique=False)
    op.create_index("ix_ai_memories_is_active", "ai_memories", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_memories_is_active", table_name="ai_memories")
    op.drop_index("ix_ai_memories_key", table_name="ai_memories")
    op.drop_index("ix_ai_memories_category", table_name="ai_memories")
    op.drop_index("ix_ai_memories_conversation_id", table_name="ai_memories")
    op.drop_index("ix_ai_memories_user_id", table_name="ai_memories")
    op.drop_table("ai_memories")
