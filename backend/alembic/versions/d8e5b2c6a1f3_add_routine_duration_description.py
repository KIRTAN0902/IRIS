"""Add a usual duration and a description to routines.

Revision ID: d8e5b2c6a1f3
Revises: c3f1a9e2d784
Create Date: 2026-10-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d8e5b2c6a1f3"
down_revision = "c3f1a9e2d784"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("habits") as batch:
        batch.add_column(sa.Column("duration_min", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("habits") as batch:
        batch.drop_column("description")
        batch.drop_column("duration_min")
