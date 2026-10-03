"""AI Memory model for storing persistent conversational context and user knowledge."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AIMemory(Base):
    """Persistent memory item extracted or saved from conversations and tools."""

    __tablename__ = "ai_memories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ai_conversations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    category: Mapped[str] = mapped_column(
        String(50), default="GENERAL", index=True, nullable=False
    )  # PREFERENCE, FACT, PROJECT, CONSTRAINT, INSTRUCTION, GENERAL
    key: Mapped[str | None] = mapped_column(
        String(120), index=True, nullable=True
    )  # Short semantic identifier, e.g. "deep_work_window", "startup_pivot"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)  # 0.0 to 1.0
    confidence: Mapped[float] = mapped_column(Float, default=0.9, nullable=False)  # 0.0 to 1.0
    source: Mapped[str] = mapped_column(
        String(50), default="CONVERSATION_EXTRACTED", nullable=False
    )  # CONVERSATION_EXTRACTED, AGENT_TOOL, USER_EXPLICIT
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", index=True, nullable=False
    )
    access_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="memories")
    conversation = relationship("AIConversation", back_populates="memories")
