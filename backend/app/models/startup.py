"""Startup model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import StartupStatus


class Startup(Base):
    __tablename__ = "startups"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    current_objective: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(
        String(15), default=StartupStatus.BUILDING.value, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    user = relationship("User", back_populates="startups")
    leads = relationship("Lead", back_populates="startup", cascade="all, delete-orphan")
    outreach_activities = relationship(
        "OutreachActivity", back_populates="startup", cascade="all, delete-orphan"
    )
    experiments = relationship("Experiment", back_populates="startup", cascade="all, delete-orphan")
    metrics = relationship("Metric", back_populates="startup")
