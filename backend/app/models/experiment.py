"""Experiment model -- startup growth experiments."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ExperimentStatus


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    startup_id: Mapped[int] = mapped_column(
        ForeignKey("startups.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    hypothesis: Mapped[str | None] = mapped_column(Text, default=None)
    action: Mapped[str | None] = mapped_column(Text, default=None)
    target: Mapped[str | None] = mapped_column(String(255), default=None)
    metric: Mapped[str | None] = mapped_column(String(120), default=None)
    result: Mapped[str | None] = mapped_column(Text, default=None)
    conclusion: Mapped[str | None] = mapped_column(Text, default=None)
    next_action: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(
        String(15), default=ExperimentStatus.PLANNED.value, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    startup = relationship("Startup", back_populates="experiments")
