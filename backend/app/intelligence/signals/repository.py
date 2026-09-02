"""Signal Repository -- handles aggregation from providers and database persistence."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.signals.base import SignalData, SignalProvider, SignalQuery
from app.intelligence.signals.providers import DEFAULT_SIGNAL_PROVIDERS
from app.intelligence.signals.relevance import filter_relevant_signals
from app.models.signal import Signal
from app.models.user import User


class SignalRepository:
    """Aggregates and persists cross-domain signals."""

    def __init__(self, providers: list[SignalProvider] | None = None):
        self.providers = providers if providers is not None else DEFAULT_SIGNAL_PROVIDERS

    def gather_all_signals(
        self,
        db: Session,
        user: User,
        query: SignalQuery,
    ) -> list[SignalData]:
        """Gather signals across all registered domain providers and stored signals."""
        collected: list[SignalData] = []

        # 1. Gather from dynamic providers
        for p in self.providers:
            if query.domains and p.domain not in query.domains:
                continue
            try:
                domain_signals = p.get_signals(db, user, query)
                collected.extend(domain_signals)
            except Exception:
                pass

        # 2. Gather from DB stored signals
        db_query = db.query(Signal).filter(Signal.user_id == user.id)
        if query.active_only:
            db_query = db_query.filter(Signal.is_active.is_(True))
        if query.domains:
            db_query = db_query.filter(Signal.domain.in_(query.domains))

        stored = db_query.order_by(Signal.timestamp.desc()).limit(query.limit).all()
        for s in stored:
            collected.append(
                SignalData(
                    domain=s.domain,
                    signal_type=s.signal_type,
                    title=s.title,
                    source=s.source,
                    provenance=s.provenance,
                    importance=s.importance,
                    urgency=s.urgency,
                    timestamp=s.timestamp,
                    summary=s.summary,
                    expires_at=s.expires_at,
                    payload=s.payload or {},
                    is_active=s.is_active,
                    id=s.id,
                )
            )

        # 3. Filter and rank for relevance
        return filter_relevant_signals(
            collected,
            query.now_utc,
            min_importance=query.min_importance,
            limit=query.limit,
        )

    def persist_signal(
        self,
        db: Session,
        user_id: int,
        data: SignalData,
    ) -> Signal:
        """Store a signal into the database."""
        row = Signal(
            user_id=user_id,
            domain=data.domain,
            signal_type=data.signal_type,
            source=data.source,
            provenance=data.provenance,
            importance=data.importance,
            urgency=data.urgency,
            title=data.title,
            summary=data.summary,
            payload=data.payload,
            timestamp=data.timestamp,
            expires_at=data.expires_at,
            is_active=data.is_active,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


# Default singleton
signal_repo = SignalRepository()
