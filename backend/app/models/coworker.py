"""Persistent coworker configuration, assignments, approvals and event history."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Coworker(Base):
    __tablename__ = "coworkers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(String(80))
    specialisation: Mapped[str] = mapped_column(String(120), default="general")
    responsibilities: Mapped[list] = mapped_column(JSON, default=list)
    system_instructions: Mapped[str] = mapped_column(Text, default="")
    preferred_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    preferred_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    allowed_capabilities: Mapped[list] = mapped_column(JSON, default=list)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("coding_projects.id", ondelete="SET NULL"), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("remote_workspaces.id", ondelete="SET NULL"), nullable=True)
    permission_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="idle")
    availability: Mapped[bool] = mapped_column(default=True)
    config_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CoworkerTask(Base):
    __tablename__ = "coworker_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    coworker_id: Mapped[str] = mapped_column(ForeignKey("coworkers.id", ondelete="CASCADE"), index=True)
    parent_task_id: Mapped[str | None] = mapped_column(ForeignKey("coworker_tasks.id", ondelete="SET NULL"), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("coding_projects.id", ondelete="SET NULL"), nullable=True)
    instruction: Mapped[str] = mapped_column(Text)
    objectives: Mapped[list] = mapped_column(JSON, default=list)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    required_capabilities: Mapped[list] = mapped_column(JSON, default=list)
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    permission_scope: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    remote_workspace_id: Mapped[str | None] = mapped_column(ForeignKey("remote_workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    coding_task_id: Mapped[str | None] = mapped_column(ForeignKey("coding_tasks.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CoworkerSession(Base):
    __tablename__ = "coworker_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("coworker_tasks.id", ondelete="CASCADE"), index=True)
    coworker_id: Mapped[str] = mapped_column(ForeignKey("coworkers.id", ondelete="CASCADE"))
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    output: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CoworkerEvent(Base):
    __tablename__ = "coworker_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    coworker_id: Mapped[str] = mapped_column(ForeignKey("coworkers.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("coworker_tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class CoworkerApproval(Base):
    __tablename__ = "coworker_approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    coworker_id: Mapped[str] = mapped_column(ForeignKey("coworkers.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("coworker_tasks.id", ondelete="CASCADE"), index=True)
    capability: Mapped[str] = mapped_column(String(120))
    action: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    approver: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


Index("ix_coworker_tasks_owner_status", CoworkerTask.user_id, CoworkerTask.coworker_id, CoworkerTask.status)
Index("ix_coworker_approvals_user_status", CoworkerApproval.user_id, CoworkerApproval.status)
