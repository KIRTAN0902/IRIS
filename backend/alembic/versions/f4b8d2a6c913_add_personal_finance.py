"""Add personal finance: transactions, budgets, bills and savings goals.

Revision ID: f4b8d2a6c913
Revises: e7a2c4f19b30
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f4b8d2a6c913"
down_revision = "e7a2c4f19b30"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "finance_bills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("account", sa.String(20), nullable=False),
        sa.Column("frequency", sa.String(12), nullable=False),
        sa.Column("next_due", sa.Date(), nullable=False),
        sa.Column("last_paid_on", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_finance_bills_user_id", "finance_bills", ["user_id"])
    op.create_index("ix_finance_bills_next_due", "finance_bills", ["next_due"])

    op.create_table(
        "finance_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("account", sa.String(20), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("bill_id", sa.Integer(), sa.ForeignKey("finance_bills.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
    )
    for col in ("user_id", "kind", "category", "occurred_on", "bill_id"):
        op.create_index(f"ix_finance_transactions_{col}", "finance_transactions", [col])

    op.create_table(
        "finance_budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("monthly_limit", sa.Numeric(12, 2), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "category", name="uq_finance_budget_category"),
    )
    op.create_index("ix_finance_budgets_user_id", "finance_budgets", ["user_id"])

    op.create_table(
        "savings_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("target_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("saved_amount", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_savings_goals_user_id", "savings_goals", ["user_id"])


def downgrade() -> None:
    op.drop_table("savings_goals")
    op.drop_table("finance_budgets")
    op.drop_table("finance_transactions")
    op.drop_table("finance_bills")
