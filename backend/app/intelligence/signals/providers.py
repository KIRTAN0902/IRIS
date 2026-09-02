"""Internal Domain Signal Providers and External Service Extension Stubs."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.intelligence.signals.base import SignalData, SignalProvider, SignalQuery
from app.models.enums import (
    GoalStatus,
    InformationProvenance,
    LifeArea,
    SignalDomain,
    SignalSource,
    SignalType,
    TaskPriority,
    TaskStatus,
)
from app.models.goal import Goal
from app.models.lead import Lead
from app.models.recurring_schedule import RecurringSchedule
from app.models.task import Task
from app.models.user import User
from app.services import analytics_service
from app.utils.datetime import minutes_between


class TaskSignalProvider(SignalProvider):
    """Derives signals from open, urgent, or blocked tasks."""

    domain: str = SignalDomain.TASKS.value

    def get_signals(
        self,
        db: Session,
        user: User,
        query: SignalQuery,
    ) -> list[SignalData]:
        now = query.now_utc
        tasks = (
            db.query(Task)
            .filter(
                Task.user_id == user.id,
                Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]),
            )
            .all()
        )

        signals: list[SignalData] = []
        for t in tasks:
            # 1. Overdue or imminent deadline signal
            if t.is_overdue:
                signals.append(
                    SignalData(
                        domain=SignalDomain.TASKS.value,
                        signal_type=SignalType.DEADLINE_APPROACHING.value,
                        source=SignalSource.INTERNAL_TASKS.value,
                        provenance=InformationProvenance.SYSTEM_DERIVED.value,
                        importance=0.9,
                        urgency=1.0,
                        title=f"Overdue task: {t.title}",
                        summary=f"Task in {t.area} is overdue.",
                        timestamp=now,
                        expires_at=now + timedelta(hours=24),
                        payload={
                            "task_id": t.id,
                            "area": t.area,
                            "priority": t.priority,
                            "deadline": t.deadline.isoformat() if t.deadline else None,
                        },
                    )
                )
            elif t.deadline:
                m = minutes_between(now, t.deadline)
                if m <= 24 * 60:
                    urgency_val = max(0.6, 1.0 - (m / (24 * 60)))
                    signals.append(
                        SignalData(
                            domain=SignalDomain.TASKS.value,
                            signal_type=SignalType.DEADLINE_APPROACHING.value,
                            source=SignalSource.INTERNAL_TASKS.value,
                            provenance=InformationProvenance.SYSTEM_DERIVED.value,
                            importance=0.85 if t.priority == TaskPriority.CRITICAL.value else 0.75,
                            urgency=round(urgency_val, 2),
                            title=f"Upcoming deadline: {t.title}",
                            summary=f"Due in {m // 60}h {m % 60}m ({t.area}).",
                            timestamp=now,
                            expires_at=t.deadline,
                            payload={
                                "task_id": t.id,
                                "area": t.area,
                                "priority": t.priority,
                                "minutes_remaining": m,
                            },
                        )
                    )

            # 2. Critical priority without immediate deadline
            elif t.priority == TaskPriority.CRITICAL.value:
                signals.append(
                    SignalData(
                        domain=SignalDomain.TASKS.value,
                        signal_type=SignalType.ANOMALY_DETECTED.value,
                        source=SignalSource.INTERNAL_TASKS.value,
                        provenance=InformationProvenance.USER_PROVIDED.value,
                        importance=0.9,
                        urgency=0.8,
                        title=f"Critical priority task: {t.title}",
                        summary=f"Marked critical in {t.area}.",
                        timestamp=now,
                        payload={"task_id": t.id, "area": t.area},
                    )
                )

        return signals


class GoalSignalProvider(SignalProvider):
    """Derives signals from goal trajectories, bottlenecks, and milestones."""

    domain: str = SignalDomain.GOALS.value

    def get_signals(
        self,
        db: Session,
        user: User,
        query: SignalQuery,
    ) -> list[SignalData]:
        now = query.now_utc
        goals = (
            db.query(Goal)
            .filter(
                Goal.user_id == user.id,
                Goal.status.in_([GoalStatus.ACTIVE.value, GoalStatus.BEHIND.value]),
            )
            .all()
        )

        signals: list[SignalData] = []
        for g in goals:
            if g.status == GoalStatus.BEHIND.value or (
                g.target_value and g.progress_fraction < 0.4
            ):
                signals.append(
                    SignalData(
                        domain=SignalDomain.GOALS.value,
                        signal_type=SignalType.GOAL_BEHIND.value,
                        source=SignalSource.INTERNAL_GOALS.value,
                        provenance=InformationProvenance.SYSTEM_DERIVED.value,
                        importance=0.85 if g.area == LifeArea.STARTUP.value else 0.7,
                        urgency=0.75,
                        title=f"Goal behind target: {g.name}",
                        summary=f"{g.area} goal progress is at {g.progress_fraction * 100:.0f}%.",
                        timestamp=now,
                        payload={
                            "goal_id": g.id,
                            "area": g.area,
                            "current_value": g.current_value,
                            "target_value": g.target_value,
                            "progress_pct": round(g.progress_fraction * 100, 1),
                        },
                    )
                )
            elif g.target_value and g.progress_fraction >= 0.8:
                signals.append(
                    SignalData(
                        domain=SignalDomain.GOALS.value,
                        signal_type=SignalType.STATUS_UPDATE.value,
                        source=SignalSource.INTERNAL_GOALS.value,
                        provenance=InformationProvenance.SYSTEM_DERIVED.value,
                        importance=0.6,
                        urgency=0.5,
                        title=f"Goal near completion: {g.name}",
                        summary=f"Achieved {g.progress_fraction * 100:.0f}% of target.",
                        timestamp=now,
                        payload={"goal_id": g.id, "area": g.area},
                    )
                )

        return signals


class ScheduleSignalProvider(SignalProvider):
    """Derives signals from recurring commitments and schedule blocks."""

    domain: str = SignalDomain.CALENDAR.value

    def get_signals(
        self,
        db: Session,
        user: User,
        query: SignalQuery,
    ) -> list[SignalData]:
        now = query.now_utc
        schedules = (
            db.query(RecurringSchedule)
            .filter(
                RecurringSchedule.user_id == user.id,
                RecurringSchedule.status == "ACTIVE",
            )
            .all()
        )

        signals: list[SignalData] = []
        for s in schedules:
            if s.is_hard_constraint:
                signals.append(
                    SignalData(
                        domain=SignalDomain.CALENDAR.value,
                        signal_type=SignalType.MEETING_UPCOMING.value,
                        source=SignalSource.INTERNAL_SCHEDULE.value,
                        provenance=InformationProvenance.USER_PROVIDED.value,
                        importance=0.8,
                        urgency=0.6,
                        title=f"Scheduled commitment: {s.name}",
                        summary=f"{s.start_time} - {s.end_time} ({s.type})",
                        timestamp=now,
                        payload={
                            "schedule_id": s.id,
                            "start_time": s.start_time,
                            "end_time": s.end_time,
                            "days": s.days_of_week,
                        },
                    )
                )

        return signals


class StartupSignalProvider(SignalProvider):
    """Derives signals from lead outreach, pipeline velocity, and active experiments."""

    domain: str = SignalDomain.STARTUP.value

    def get_signals(
        self,
        db: Session,
        user: User,
        query: SignalQuery,
    ) -> list[SignalData]:
        now = query.now_utc
        signals: list[SignalData] = []

        # 1. Inbound lead reply or meeting interest
        replied_leads = (
            db.query(Lead)
            .filter(
                Lead.startup.has(user_id=user.id),
                Lead.status.in_(["REPLIED", "INTERESTED", "MEETING"]),
            )
            .all()
        )

        for lead_item in replied_leads:
            signals.append(
                SignalData(
                    domain=SignalDomain.STARTUP.value,
                    signal_type=SignalType.OPPORTUNITY_INBOUND.value,
                    source=SignalSource.INTERNAL_STARTUP.value,
                    provenance=InformationProvenance.SYSTEM_DERIVED.value,
                    importance=0.95,
                    urgency=0.85,
                    title=f"Founder interest: {lead_item.name} ({lead_item.company})",
                    summary=f"Status: {lead_item.status}. Next follow-up due.",
                    timestamp=now,
                    payload={
                        "lead_id": lead_item.id,
                        "lead_name": lead_item.name,
                        "company": lead_item.company,
                        "status": lead_item.status,
                    },
                )
            )

        # 2. Startup metrics velocity
        try:
            sa = analytics_service.startup_analytics(db, user.id)
            if sa.conversion_rate < 0.15 and sa.total_leads > 0:
                conv_pct = sa.conversion_rate * 100
                signals.append(
                    SignalData(
                        domain=SignalDomain.STARTUP.value,
                        signal_type=SignalType.GOAL_BEHIND.value,
                        source=SignalSource.INTERNAL_STARTUP.value,
                        provenance=InformationProvenance.SYSTEM_DERIVED.value,
                        importance=0.85,
                        urgency=0.7,
                        title="Startup bottleneck: Outreach validation behind pace",
                        summary=f"{sa.total_leads} leads with {conv_pct:.1f}% reply rate.",
                        timestamp=now,
                        payload=sa.model_dump(),
                    )
                )
        except Exception:
            pass

        return signals


# --- Stubs for Future External Integrations (No fake data / No fabricated signals) ---


class EmailSignalProvider(SignalProvider):
    """Stub provider for future Gmail / Email integrations."""

    domain: str = SignalDomain.EMAIL.value

    def get_signals(
        self,
        db: Session,
        user: User,
        query: SignalQuery,
    ) -> list[SignalData]:
        # Return empty until OAuth is connected; never fabricate inbox data.
        return []


class FinanceSignalProvider(SignalProvider):
    """Stub provider for future Finance integrations."""

    domain: str = SignalDomain.FINANCE.value

    def get_signals(
        self,
        db: Session,
        user: User,
        query: SignalQuery,
    ) -> list[SignalData]:
        # Return empty until Finance service is connected.
        return []


DEFAULT_SIGNAL_PROVIDERS: list[SignalProvider] = [
    TaskSignalProvider(),
    GoalSignalProvider(),
    ScheduleSignalProvider(),
    StartupSignalProvider(),
    EmailSignalProvider(),
    FinanceSignalProvider(),
]
