"""Signal relevance filtering, expiration checks, and time decay."""

from __future__ import annotations

from datetime import datetime

from app.intelligence.signals.base import SignalData


def filter_relevant_signals(
    signals: list[SignalData],
    now_utc: datetime,
    *,
    min_importance: float = 0.0,
    limit: int = 25,
) -> list[SignalData]:
    """Filter, decay, rank, and limit cross-domain signals for AI/decision consumption."""
    relevant: list[tuple[float, SignalData]] = []

    for s in signals:
        # 1. Expiration check
        if s.expires_at and s.expires_at < now_utc:
            continue
        if not s.is_active:
            continue

        # 2. Importance threshold
        if s.importance < min_importance:
            continue

        # 3. Time decay calculation
        age_hours = max(0.0, (now_utc - s.timestamp).total_seconds() / 3600.0)
        # Decay slowly (e.g. 5% per hour of age, floor at 0.5x)
        decay_factor = max(0.5, 1.0 / (1.0 + age_hours * 0.05))
        effective_score = s.composite_score * decay_factor

        relevant.append((effective_score, s))

    # Sort descending by effective score
    relevant.sort(key=lambda x: x[0], reverse=True)

    return [s for _, s in relevant[:limit]]
