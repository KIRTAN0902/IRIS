"""User model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    facts: Mapped[dict | None] = mapped_column(JSON, default=dict)
    preferences: Mapped[dict | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    time_blocks = relationship("TimeBlock", back_populates="user", cascade="all, delete-orphan")
    calendar_events = relationship(
        "CalendarEvent", back_populates="user", cascade="all, delete-orphan"
    )
    focus_sessions = relationship(
        "FocusSession", back_populates="user", cascade="all, delete-orphan"
    )
    daily_reviews = relationship("DailyReview", back_populates="user", cascade="all, delete-orphan")
    startups = relationship("Startup", back_populates="user", cascade="all, delete-orphan")
    metrics = relationship("Metric", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship(
        "AIConversation", back_populates="user", cascade="all, delete-orphan"
    )
    recurring_schedules = relationship(
        "RecurringSchedule", back_populates="user", cascade="all, delete-orphan"
    )
    signals = relationship("Signal", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("AIMemory", back_populates="user", cascade="all, delete-orphan")
    email_accounts = relationship(
        "EmailAccount", back_populates="user", cascade="all, delete-orphan"
    )
    mesh_pairings = relationship(
        "MeshPairing", back_populates="user", cascade="all, delete-orphan"
    )
    mesh_relay_messages = relationship(
        "MeshRelayMessage", back_populates="user", cascade="all, delete-orphan"
    )

