"""add recurring schedules table

Revision ID: b71e88d022f3
Revises: a82f33c091e2
Create Date: 2026-08-30 20:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b71e88d022f3'
down_revision: Union[str, None] = 'a82f33c091e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'recurring_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=30), nullable=False),
        sa.Column('days_of_week', sa.String(length=64), nullable=False),
        sa.Column('start_time', sa.String(length=10), nullable=False),
        sa.Column('end_time', sa.String(length=10), nullable=False),
        sa.Column('is_hard_constraint', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ACTIVE'),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('recurring_schedules', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recurring_schedules_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_recurring_schedules_type'), ['type'], unique=False)
        batch_op.create_index(batch_op.f('ix_recurring_schedules_status'), ['status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('recurring_schedules', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recurring_schedules_status'))
        batch_op.drop_index(batch_op.f('ix_recurring_schedules_type'))
        batch_op.drop_index(batch_op.f('ix_recurring_schedules_user_id'))
    op.drop_table('recurring_schedules')
