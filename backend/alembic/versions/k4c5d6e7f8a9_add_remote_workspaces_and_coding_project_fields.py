"""Add remote workspaces table, coworker workspace link, and coding project git repo fields.

Revision ID: k4c5d6e7f8a9
Revises: j3b4c5d6e7f8
Create Date: 2026-11-06 12:48:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "k4c5d6e7f8a9"
down_revision = "j3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create remote_workspaces table
    op.create_table(
        "remote_workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("coding_projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False, server_default="Remote Workspace"),
        sa.Column("repo_url", sa.String(512), nullable=False),
        sa.Column("branch", sa.String(128), nullable=False, server_default="main"),
        sa.Column("task_branch", sa.String(128), nullable=True),
        sa.Column("base_commit_sha", sa.String(64), nullable=True),
        sa.Column("current_commit_sha", sa.String(64), nullable=True),
        sa.Column("uncommitted_patch", sa.Text(), nullable=True),
        sa.Column("previous_patch", sa.Text(), nullable=True),
        sa.Column("checkpoint_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkpoint_hash", sa.String(64), nullable=True),
        sa.Column("checkpoint_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="idle"),
        sa.Column("storage_type", sa.String(32), nullable=False, server_default="git_backed"),
        sa.Column("engine_name", sa.String(80), nullable=False, server_default="antigravity"),
        sa.Column("engine_session_id", sa.String(120), nullable=True),
        sa.Column("companion_url", sa.String(512), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_active_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_remote_workspaces_user_id", "remote_workspaces", ["user_id"])
    op.create_index("ix_remote_workspaces_project_id", "remote_workspaces", ["project_id"])
    op.create_index("ix_remote_workspaces_status", "remote_workspaces", ["status"])

    # 2. Add workspace_id column to coworkers
    op.add_column("coworkers", sa.Column("workspace_id", sa.String(36), sa.ForeignKey("remote_workspaces.id", ondelete="SET NULL"), nullable=True))

    # 3. Add remote_workspace_id column to coworker_tasks
    op.add_column("coworker_tasks", sa.Column("remote_workspace_id", sa.String(36), sa.ForeignKey("remote_workspaces.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_coworker_tasks_remote_workspace_id", "coworker_tasks", ["remote_workspace_id"])

    # 4. Add git_repo_url and default_branch to coding_projects
    op.add_column("coding_projects", sa.Column("git_repo_url", sa.String(512), nullable=True))
    op.add_column("coding_projects", sa.Column("default_branch", sa.String(128), nullable=True, server_default="main"))


def downgrade() -> None:
    op.drop_column("coding_projects", "default_branch")
    op.drop_column("coding_projects", "git_repo_url")
    op.drop_column("coworkers", "workspace_id")
    op.drop_index("ix_remote_workspaces_status", table_name="remote_workspaces")
    op.drop_index("ix_remote_workspaces_project_id", table_name="remote_workspaces")
    op.drop_index("ix_remote_workspaces_user_id", table_name="remote_workspaces")
    op.drop_table("remote_workspaces")
