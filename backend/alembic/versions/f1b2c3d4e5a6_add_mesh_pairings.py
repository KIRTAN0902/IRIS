"""Add mesh pairings and mesh relay messages tables.

Revision ID: f1b2c3d4e5a6
Revises: e9a1c2d3b4f5
Create Date: 2026-10-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1b2c3d4e5a6"
down_revision = "e9a1c2d3b4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mesh_pairings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("device_name", sa.String(120), nullable=False),
        sa.Column("device_type", sa.String(32), server_default="phone_mobile", nullable=False),
        sa.Column("pairing_code", sa.String(8), nullable=True),
        sa.Column("pairing_code_expires_at", sa.DateTime(), nullable=True),
        sa.Column("pairing_token", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("battery_level", sa.Integer(), nullable=True),
        sa.Column("is_charging", sa.Boolean(), nullable=True),
        sa.Column("paired_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "device_id", name="uq_user_device_pairing"),
    )
    op.create_index("ix_mesh_pairings_user_id", "mesh_pairings", ["user_id"])
    op.create_index("ix_mesh_pairings_device_id", "mesh_pairings", ["device_id"])
    op.create_index("ix_mesh_pairings_pairing_code", "mesh_pairings", ["pairing_code"])
    op.create_index("ix_mesh_pairings_pairing_token", "mesh_pairings", ["pairing_token"], unique=True)
    op.create_index("ix_mesh_pairings_last_seen_at", "mesh_pairings", ["last_seen_at"])

    op.create_table(
        "mesh_relay_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_device_id", sa.String(64), nullable=False),
        sa.Column("target_device_id", sa.String(64), nullable=True),
        sa.Column("msg_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("consumed_by", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mesh_relay_messages_user_id", "mesh_relay_messages", ["user_id"])
    op.create_index("ix_mesh_relay_messages_sender_device_id", "mesh_relay_messages", ["sender_device_id"])
    op.create_index("ix_mesh_relay_messages_target_device_id", "mesh_relay_messages", ["target_device_id"])
    op.create_index("ix_mesh_relay_messages_msg_type", "mesh_relay_messages", ["msg_type"])
    op.create_index("ix_mesh_relay_messages_created_at", "mesh_relay_messages", ["created_at"])


def downgrade() -> None:
    op.drop_table("mesh_relay_messages")
    op.drop_table("mesh_pairings")
