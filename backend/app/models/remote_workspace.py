"""Persistent remote workspace model for Coding Co-worker."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class RemoteWorkspace(Base):
    __tablename__ = "remote_workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("coding_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="Remote Workspace")
    repo_url: Mapped[str] = mapped_column(String(512))
    branch: Mapped[str] = mapped_column(String(128), default="main")
    task_branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    base_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uncommitted_patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint_version: Mapped[int] = mapped_column(default=0)
    checkpoint_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="idle", index=True)
    storage_type: Mapped[str] = mapped_column(String(32), default="git_backed")
    engine_name: Mapped[str] = mapped_column(String(80), default="antigravity")
    engine_session_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    companion_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
