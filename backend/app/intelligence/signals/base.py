"""Base data structures and protocols for cross-domain signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.models.enums import InformationProvenance, SignalSource
from app.models.user import User


@dataclass
class SignalQuery:
    """Parameters for querying signals across internal and external domains."""

    user_id: int
    now_utc: datetime
    domains: list[str] | None = None
    min_importance: float = 0.0
    active_only: bool = True
    limit: int = 50


@dataclass
class SignalData:
    """Normalized in-memory representation of a cross-domain signal."""

    domain: str
    signal_type: str
    title: str
    source: str = SignalSource.INTERNAL_TASKS.value
    provenance: str = InformationProvenance.SYSTEM_DERIVED.value
    importance: float = 0.5  # 0.0 to 1.0
    urgency: float = 0.5  # 0.0 to 1.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    summary: str | None = None
    expires_at: datetime | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    id: int | None = None

    @property
    def composite_score(self) -> float:
        """Combined urgency and importance score."""
        return (self.urgency * 0.55) + (self.importance * 0.45)


class SignalProvider(Protocol):
    """Protocol for domain-specific signal providers."""

    domain: str

    def get_signals(
        self,
        db: Session,
        user: User,
        query: SignalQuery,
    ) -> list[SignalData]:
        """Produce normalized signals for this domain."""
        ...
