"""add user facts and preferences

Revision ID: a82f33c091e2
Revises: 147f444aa934
Create Date: 2026-08-30 19:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a82f33c091e2'
down_revision: Union[str, None] = '147f444aa934'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('facts', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('preferences', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('preferences')
        batch_op.drop_column('facts')
