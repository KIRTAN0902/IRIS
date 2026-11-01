from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class CodingTaskRecord(Base):
    __tablename__ = "coding_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("coding_projects.id", ondelete="CASCADE"))
    parent_task_id: Mapped[str | None] = mapped_column(ForeignKey("coding_tasks.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[str] = mapped_column(String(80))
    instruction: Mapped[str] = mapped_column(Text)
    brief: Mapped[dict] = mapped_column(JSON)
    approved_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="awaiting_approval")
    approval_state: Mapped[str] = mapped_column(String(20), default="pending")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    events: Mapped[list] = mapped_column(JSON, default=list)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class CodingSessionRecord(Base):
    __tablename__ = "coding_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("coding_tasks.id", ondelete="CASCADE"))
    agent_id: Mapped[str] = mapped_column(String(80))
    project_id: Mapped[int] = mapped_column(ForeignKey("coding_projects.id", ondelete="CASCADE"))
    directory: Mapped[str] = mapped_column(Text)
    manager_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_cursor: Mapped[int] = mapped_column(default=0)
    external_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    resume_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    output: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
