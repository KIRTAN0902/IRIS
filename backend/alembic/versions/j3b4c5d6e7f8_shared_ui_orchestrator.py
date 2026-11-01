"""Persist shared UI preferences, layouts, proposal decisions and rollback history."""
from alembic import op
import sqlalchemy as sa

revision = "j3b4c5d6e7f8"
down_revision = "i2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ui_workspace_configs",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("layouts", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "ui_change_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("layout", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime()),
    )
    op.create_index("ix_ui_change_proposals_user_id", "ui_change_proposals", ["user_id"])
    op.create_index("ix_ui_change_proposals_status", "ui_change_proposals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ui_change_proposals_status", table_name="ui_change_proposals")
    op.drop_index("ix_ui_change_proposals_user_id", table_name="ui_change_proposals")
    op.drop_table("ui_change_proposals")
    op.drop_table("ui_workspace_configs")
