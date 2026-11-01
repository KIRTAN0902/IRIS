"""Add registered coding workspaces and durable coding tasks/sessions."""
from alembic import op
import sqlalchemy as sa

revision = "h1a2b3c4d5e6"
down_revision = "g2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("coding_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("directory", sa.Text(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("read_access", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("write_access", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("command_access", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allowed_commands", sa.JSON(), nullable=False),
        sa.Column("allowed_domains", sa.JSON(), nullable=False),
        sa.Column("network_access", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_accessed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_coding_projects_user_id", "coding_projects", ["user_id"])
    op.create_table("coding_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("coding_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_task_id", sa.String(36), sa.ForeignKey("coding_tasks.id", ondelete="SET NULL")),
        sa.Column("agent_id", sa.String(80), nullable=False), sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("brief", sa.JSON(), nullable=False), sa.Column("approved_prompt", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("approval_state", sa.String(20), nullable=False),
        sa.Column("result", sa.JSON()), sa.Column("verification", sa.JSON()), sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("session_id", sa.String(36)), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime()), sa.Column("ended_at", sa.DateTime()))
    op.create_index("ix_coding_tasks_user_id", "coding_tasks", ["user_id"])
    op.create_table("coding_sessions",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("task_id", sa.String(36), sa.ForeignKey("coding_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(80), nullable=False), sa.Column("project_id", sa.Integer(), sa.ForeignKey("coding_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("directory", sa.Text(), nullable=False), sa.Column("external_session_id", sa.String(255)),
        sa.Column("manager_key", sa.String(36)),
        sa.Column("event_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("resume_supported", sa.Boolean(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False), sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime()), sa.Column("ended_at", sa.DateTime()))


def downgrade() -> None:
    op.drop_table("coding_sessions")
    op.drop_index("ix_coding_tasks_user_id", table_name="coding_tasks")
    op.drop_table("coding_tasks")
    op.drop_index("ix_coding_projects_user_id", table_name="coding_projects")
    op.drop_table("coding_projects")
