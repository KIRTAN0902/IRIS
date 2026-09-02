"""Signal model -- normalized cross-domain input signal for IRIS Decision Intelligence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(50), index=True)
    signal_type: Mapped[str] = mapped_column(String(50), index=True)
    source: Mapped[str] = mapped_column(String(50), default="INTERNAL_TASKS")
    provenance: Mapped[str] = mapped_column(String(50), default="SYSTEM_DERIVED")
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    urgency: Mapped[float] = mapped_column(Float, default=0.5)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )

    user = relationship("User", back_populates="signals")

    __table_args__ = (Index("ix_signals_user_domain_active", "user_id", "domain", "is_active"),)
