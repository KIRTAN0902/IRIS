"""Add gym workout plans, their exercises and per-day exercise tick-offs.

Revision ID: c3f1a9e2d784
Revises: a6d2e8f1c457
Create Date: 2026-10-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3f1a9e2d784"
down_revision = "a6d2e8f1c457"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("focus", sa.String(160), nullable=True),
        sa.Column("days_of_week", sa.String(64), nullable=False),
        sa.Column("duration", sa.String(40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workouts_user_id", "workouts", ["user_id"])

    op.create_table(
        "workout_exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workout_id", sa.Integer(), sa.ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("sets_reps", sa.String(40), nullable=True),
        sa.Column("time", sa.String(40), nullable=True),
        sa.Column("muscles", sa.String(160), nullable=True),
        sa.Column("weight", sa.String(40), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
    )
    op.create_index("ix_workout_exercises_workout_id", "workout_exercises", ["workout_id"])

    op.create_table(
        "workout_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workout_id", sa.Integer(), sa.ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("workout_exercises.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("exercise_id", "day", name="uq_workout_log_day"),
    )
    for col in ("user_id", "workout_id", "exercise_id", "day"):
        op.create_index(f"ix_workout_logs_{col}", "workout_logs", [col])


def downgrade() -> None:
    op.drop_table("workout_logs")
    op.drop_table("workout_exercises")
    op.drop_table("workouts")
