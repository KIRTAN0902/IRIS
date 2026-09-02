"""Unit tests for Signal Layer and Attention Engine (Phase 3)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.intelligence.attention_engine import (
    compute_attention_score,
    generate_attention_items,
)
from app.intelligence.signals.base import SignalData, SignalQuery
from app.intelligence.signals.providers import (
    EmailSignalProvider,
    FinanceSignalProvider,
    GoalSignalProvider,
    TaskSignalProvider,
)
from app.intelligence.signals.relevance import filter_relevant_signals
from app.models.enums import (
    GoalStatus,
    LifeArea,
    SignalDomain,
    SignalType,
    TaskPriority,
)
from app.models.user import User
from app.utils.datetime import utcnow
from tests.conftest import hours_from_now, make_goal, make_task


def test_signal_data_composite_score():
    """Verify SignalData composite score calculation."""
    sig = SignalData(
        domain=SignalDomain.STARTUP.value,
        signal_type=SignalType.OPPORTUNITY_INBOUND.value,
        title="Founder demo request",
        importance=0.9,
        urgency=0.8,
    )
    # 0.8 * 0.55 + 0.9 * 0.45 = 0.44 + 0.405 = 0.845
    assert 0.84 <= sig.composite_score <= 0.85


def test_signal_relevance_filtering_and_decay():
    """Verify expiration filtering and age decay."""
    now = datetime(2026, 8, 31, 12, 0)
    sig_fresh = SignalData(
        domain=SignalDomain.STARTUP.value,
        signal_type=SignalType.OPPORTUNITY_INBOUND.value,
        title="Fresh inquiry",
        importance=0.9,
        urgency=0.9,
        timestamp=now,
    )
    sig_old = SignalData(
        domain=SignalDomain.TASKS.value,
        signal_type=SignalType.DEADLINE_APPROACHING.value,
        title="Old task signal",
        importance=0.9,
        urgency=0.9,
        timestamp=now - timedelta(hours=20),
    )
    sig_expired = SignalData(
        domain=SignalDomain.TASKS.value,
        signal_type=SignalType.DEADLINE_APPROACHING.value,
        title="Expired signal",
        importance=0.9,
        urgency=0.9,
        timestamp=now - timedelta(hours=2),
        expires_at=now - timedelta(minutes=10),
    )

    filtered = filter_relevant_signals(
        [sig_fresh, sig_old, sig_expired], now_utc=now, min_importance=0.5
    )
    assert len(filtered) == 2
    assert filtered[0].title == "Fresh inquiry"
    assert filtered[1].title == "Old task signal"
    assert filtered[0].composite_score > filtered[1].composite_score * 0.5


def test_task_signal_provider(db, user_id):
    """TaskSignalProvider derives signals for urgent and overdue tasks."""
    user = db.query(User).filter(User.id == user_id).first()
    make_task(
        db,
        user_id,
        title="Overdue report",
        area=LifeArea.COLLEGE.value,
        deadline=utcnow() - timedelta(hours=2),
    )
    make_task(
        db,
        user_id,
        title="Urgent deliverable",
        area=LifeArea.INTERNSHIP.value,
        deadline=hours_from_now(3),
    )

    provider = TaskSignalProvider()
    query = SignalQuery(user_id=user.id, now_utc=utcnow())
    signals = provider.get_signals(db, user, query)

    assert len(signals) >= 2
    titles = [s.title for s in signals]
    assert any("Overdue" in t for t in titles)
    assert any("Upcoming" in t for t in titles)


def test_goal_signal_provider(db, user_id):
    """GoalSignalProvider derives signals for behind goals."""
    user = db.query(User).filter(User.id == user_id).first()
    make_goal(
        db,
        user_id,
        name="100 customer conversations",
        target_value=100,
        current_value=15,
        status=GoalStatus.BEHIND.value,
    )

    provider = GoalSignalProvider()
    query = SignalQuery(user_id=user.id, now_utc=utcnow())
    signals = provider.get_signals(db, user, query)

    assert len(signals) >= 1
    assert any("behind" in s.title.lower() for s in signals)


def test_external_stubs_never_fabricate():
    """Email and Finance stubs return empty until real integration is connected."""
    email_prov = EmailSignalProvider()
    finance_prov = FinanceSignalProvider()
    query = SignalQuery(user_id=1, now_utc=utcnow())

    assert email_prov.get_signals(None, None, query) == []
    assert finance_prov.get_signals(None, None, query) == []


def test_attention_scoring_formula():
    """Verify deterministic attention score bounds and weighting."""
    score_imminent = compute_attention_score(
        urgency=1.0,
        impact=0.9,
        domain=SignalDomain.STARTUP.value,
        minutes_to_deadline=30,
    )
    # 35 + 22.5 + 15 + 25 = 97.5
    assert 95 <= score_imminent <= 100

    score_low = compute_attention_score(
        urgency=0.2,
        impact=0.3,
        domain=SignalDomain.PERSONAL.value,
        minutes_to_deadline=None,
    )
    # 7 + 7.5 + 5 = 19.5
    assert 15 <= score_low <= 25


def test_generate_attention_items(db, user_id):
    """generate_attention_items aggregates tasks, goals, and signals into attention items."""
    user = db.query(User).filter(User.id == user_id).first()
    make_task(
        db,
        user_id,
        title="Imminent Project Presentation",
        area=LifeArea.COLLEGE.value,
        deadline=hours_from_now(1.5),
        priority=TaskPriority.CRITICAL.value,
    )
    make_goal(
        db,
        user_id,
        name="Pilot Signups",
        target_value=10,
        current_value=1,
        status=GoalStatus.BEHIND.value,
        area=LifeArea.STARTUP.value,
    )

    sig = SignalData(
        domain=SignalDomain.STARTUP.value,
        signal_type=SignalType.OPPORTUNITY_INBOUND.value,
        title="Inbound Agency Partner Request",
        importance=0.95,
        urgency=0.9,
    )

    items = generate_attention_items(db, user, signals=[sig])
    assert len(items) >= 3
    # First item must have highest score
    assert items[0].score >= items[1].score
    assert items[0].score >= items[-1].score
