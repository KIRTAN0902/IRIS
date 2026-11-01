"""Add persistent IRIS coworkers, tasks, sessions, events and approvals."""
from alembic import op
import sqlalchemy as sa

revision = "i2a3b4c5d6e7"
down_revision = "h1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("coworkers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("role", sa.String(80), nullable=False), sa.Column("specialisation", sa.String(120), nullable=False),
        sa.Column("responsibilities", sa.JSON(), nullable=False), sa.Column("system_instructions", sa.Text(), nullable=False),
        sa.Column("preferred_provider", sa.String(80)), sa.Column("preferred_model", sa.String(160)),
        sa.Column("allowed_capabilities", sa.JSON(), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("coding_projects.id", ondelete="SET NULL")),
        sa.Column("permission_profile", sa.JSON(), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("availability", sa.Boolean(), nullable=False), sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_coworkers_user_id", "coworkers", ["user_id"])
    op.create_table("coworker_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coworker_id", sa.String(36), sa.ForeignKey("coworkers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_task_id", sa.String(36), sa.ForeignKey("coworker_tasks.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("coding_projects.id", ondelete="SET NULL")),
        sa.Column("instruction", sa.Text(), nullable=False), sa.Column("objectives", sa.JSON(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False), sa.Column("required_capabilities", sa.JSON(), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False), sa.Column("permission_scope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("result", sa.JSON()),
        sa.Column("verification", sa.JSON()), sa.Column("output", sa.Text()), sa.Column("error", sa.Text()),
        sa.Column("session_id", sa.String(36)), sa.Column("coding_task_id", sa.String(36), sa.ForeignKey("coding_tasks.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime()), sa.Column("ended_at", sa.DateTime()))
    op.create_index("ix_coworker_tasks_user_id", "coworker_tasks", ["user_id"])
    op.create_index("ix_coworker_tasks_coworker_id", "coworker_tasks", ["coworker_id"])
    op.create_index("ix_coworker_tasks_status", "coworker_tasks", ["status"])
    op.create_index("ix_coworker_tasks_owner_status", "coworker_tasks", ["user_id", "coworker_id", "status"])
    op.create_table("coworker_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("coworker_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coworker_id", sa.String(36), sa.ForeignKey("coworkers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(80)), sa.Column("model", sa.String(160)),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("output", sa.Text(), nullable=False),
        sa.Column("error", sa.Text()), sa.Column("started_at", sa.DateTime()), sa.Column("ended_at", sa.DateTime()))
    op.create_index("ix_coworker_sessions_user_id", "coworker_sessions", ["user_id"])
    op.create_index("ix_coworker_sessions_task_id", "coworker_sessions", ["task_id"])
    op.create_table("coworker_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coworker_id", sa.String(36), sa.ForeignKey("coworkers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("coworker_tasks.id", ondelete="CASCADE")),
        sa.Column("event_type", sa.String(64), nullable=False), sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    for table in ("user_id", "coworker_id", "task_id", "created_at"):
        op.create_index(f"ix_coworker_events_{table}", "coworker_events", [table])
    op.create_table("coworker_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coworker_id", sa.String(36), sa.ForeignKey("coworkers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("coworker_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capability", sa.String(120), nullable=False), sa.Column("action", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("approver", sa.String(120)), sa.Column("decision_reason", sa.Text()), sa.Column("expires_at", sa.DateTime()),
        sa.Column("decided_at", sa.DateTime()), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_coworker_approvals_user_id", "coworker_approvals", ["user_id"])
    op.create_index("ix_coworker_approvals_coworker_id", "coworker_approvals", ["coworker_id"])
    op.create_index("ix_coworker_approvals_task_id", "coworker_approvals", ["task_id"])
    op.create_index("ix_coworker_approvals_status", "coworker_approvals", ["status"])
    op.create_index("ix_coworker_approvals_user_status", "coworker_approvals", ["user_id", "status"])


def downgrade() -> None:
    op.drop_table("coworker_approvals")
    op.drop_table("coworker_events")
    op.drop_table("coworker_sessions")
    op.drop_index("ix_coworker_tasks_owner_status", table_name="coworker_tasks")
    op.drop_index("ix_coworker_tasks_status", table_name="coworker_tasks")
    op.drop_index("ix_coworker_tasks_coworker_id", table_name="coworker_tasks")
    op.drop_index("ix_coworker_tasks_user_id", table_name="coworker_tasks")
    op.drop_table("coworker_tasks")
    op.drop_index("ix_coworkers_user_id", table_name="coworkers")
    op.drop_table("coworkers")
