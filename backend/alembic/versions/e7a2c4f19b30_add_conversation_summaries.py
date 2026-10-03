"""Add rolling summaries to conversations (shared episodic memory).

Revision ID: e7a2c4f19b30
Revises: d13a55b74101
Create Date: 2026-10-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7a2c4f19b30"
down_revision = "d13a55b74101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_conversations") as batch:
        batch.add_column(sa.Column("summary", sa.Text(), nullable=True))
        batch.add_column(sa.Column("topics", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_conversations") as batch:
        batch.drop_column("topics")
        batch.drop_column("summary")
