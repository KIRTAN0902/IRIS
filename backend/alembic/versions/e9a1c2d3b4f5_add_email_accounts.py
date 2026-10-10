"""Add email accounts table for multi-account Gmail integration.

Revision ID: e9a1c2d3b4f5
Revises: d8e5b2c6a1f3
Create Date: 2026-10-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e9a1c2d3b4f5"
down_revision = "d8e5b2c6a1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(64), nullable=False),
        sa.Column("email_address", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(32), server_default="gmail", nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(), nullable=True),
        sa.Column("client_id", sa.String(255), nullable=True),
        sa.Column("client_secret", sa.String(255), nullable=True),
        sa.Column("scopes", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "alias", name="uq_user_email_account_alias"),
    )
    op.create_index("ix_email_accounts_user_id", "email_accounts", ["user_id"])
    op.create_index("ix_email_accounts_alias", "email_accounts", ["alias"])
    op.create_index("ix_email_accounts_email_address", "email_accounts", ["email_address"])


def downgrade() -> None:
    op.drop_table("email_accounts")
