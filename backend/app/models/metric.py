"""Metric model -- flexible manual/imported time-series metrics.

Prefer deriving metrics from underlying records (tasks, focus sessions,
outreach activities) via the analytics service; use this model only for
values that cannot be derived (e.g., MRR snapshots, external data).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    startup_id: Mapped[int | None] = mapped_column(
        ForeignKey("startups.id", ondelete="CASCADE"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(50), default=None)
    source: Mapped[str | None] = mapped_column(String(120), default=None)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), index=True
    )

    user = relationship("User", back_populates="metrics")
    startup = relationship("Startup", back_populates="metrics")
