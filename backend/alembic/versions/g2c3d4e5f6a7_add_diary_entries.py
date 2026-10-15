"""Add diary entries table.

Revision ID: g2c3d4e5f6a7
Revises: f1b2c3d4e5a6
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g2c3d4e5f6a7"
down_revision = "f1b2c3d4e5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diary_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(32), nullable=False, server_default="NOTE"),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mood", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_diary_entries_user_id", "diary_entries", ["user_id"])
    op.create_index("ix_diary_entries_title", "diary_entries", ["title"])
    op.create_index("ix_diary_entries_category", "diary_entries", ["category"])
    op.create_index("ix_diary_entries_is_pinned", "diary_entries", ["is_pinned"])
    op.create_index("ix_diary_entries_created_at", "diary_entries", ["created_at"])


def downgrade() -> None:
    op.drop_table("diary_entries")
