"""Attention Engine -- identifies items across life domains that deserve attention.

Deterministic attention scoring for urgent deadlines, missed goals, overdue tasks,
startup bottlenecks, schedule conflicts, and missing information.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.signals.base import SignalData
from app.models.enums import (
    AttentionItemType,
    InformationProvenance,
    LifeArea,
    SignalDomain,
    SignalType,
    TaskPriority,
    TaskStatus,
)
from app.models.goal import Goal
from app.models.task import Task
from app.models.user import User
from app.utils.datetime import minutes_between, utcnow


@dataclass
class AttentionItem:
    """A cross-domain item requiring the user's attention or action."""

    id: str
    type: str  # AttentionItemType
    domain: str  # SignalDomain
    title: str
    description: str
    score: float  # 0.0 to 100.0
    urgency: float  # 0.0 to 1.0
    impact: float  # 0.0 to 1.0
    provenance: str = InformationProvenance.SYSTEM_DERIVED.value
    deadline: datetime | None = None
    suggested_action: str | None = None
    source_id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.deadline:
            d["deadline"] = self.deadline.isoformat()
        return d


def compute_attention_score(
    *,
    urgency: float,
    impact: float,
    domain: str,
    minutes_to_deadline: int | None = None,
    age_hours: float = 0.0,
) -> float:
    """Calculate deterministic attention score (0.0 to 100.0)."""
    # 1. Base components
    urgency_part = urgency * 35.0
    impact_part = impact * 25.0

    # 2. Strategic domain weight
    if domain == SignalDomain.STARTUP.value:
        strategic_part = 15.0
    elif domain in (SignalDomain.COLLEGE.value, SignalDomain.INTERNSHIP.value):
        strategic_part = 10.0
    else:
        strategic_part = 5.0

    # 3. Deadline pressure boost
    deadline_part = 0.0
    if minutes_to_deadline is not None:
        if minutes_to_deadline <= 0:
            deadline_part = 30.0  # Overdue
        elif minutes_to_deadline <= 120:  # <= 2 hours
            deadline_part = 25.0
        elif minutes_to_deadline <= 1440:  # <= 24 hours
            deadline_part = 15.0
        elif minutes_to_deadline <= 2880:  # <= 48 hours
            deadline_part = 8.0

    # 4. Age decay
    age_decay = min(15.0, age_hours * 0.5)

    total = urgency_part + impact_part + strategic_part + deadline_part - age_decay
    return round(min(100.0, max(0.0, total)), 1)


def generate_attention_items(
    db: Session,
    user: User,
    signals: list[SignalData] | None = None,
    context: dict[str, Any] | None = None,
    now_utc: datetime | None = None,
) -> list[AttentionItem]:
    """Identify and score all active attention items for the user."""
    now = now_utc or utcnow()
    items: list[AttentionItem] = []

    # 1. Attention from Tasks (Overdue, imminent deadlines, critical blocks)
    open_tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]),
        )
        .all()
    )

    for t in open_tasks:
        if t.is_overdue:
            score = compute_attention_score(
                urgency=1.0,
                impact=0.9,
                domain=t.area,
                minutes_to_deadline=-10,
            )
            items.append(
                AttentionItem(
                    id=f"att_task_overdue_{t.id}",
                    type=AttentionItemType.OVERDUE_TASK.value,
                    domain=t.area,
                    title=f"Overdue Task: {t.title}",
                    description=f"Task was scheduled for completion and is now overdue ({t.area}).",
                    score=score,
                    urgency=1.0,
                    impact=0.9,
                    deadline=t.deadline,
                    suggested_action=f"Complete '{t.title}' or reschedule deadline.",
                    source_id=t.id,
                )
            )
        elif t.deadline:
            m = minutes_between(now, t.deadline)
            if m <= 24 * 60:
                score = compute_attention_score(
                    urgency=round(max(0.6, 1.0 - (m / (24 * 60))), 2),
                    impact=0.85 if t.priority == TaskPriority.CRITICAL.value else 0.75,
                    domain=t.area,
                    minutes_to_deadline=m,
                )
                items.append(
                    AttentionItem(
                        id=f"att_task_deadline_{t.id}",
                        type=AttentionItemType.URGENT_DEADLINE.value,
                        domain=t.area,
                        title=f"Imminent Deadline: {t.title}",
                        description=f"Due in {m // 60}h {m % 60}m ({t.area}).",
                        score=score,
                        urgency=round(max(0.6, 1.0 - (m / (24 * 60))), 2),
                        impact=0.85 if t.priority == TaskPriority.CRITICAL.value else 0.75,
                        deadline=t.deadline,
                        suggested_action=f"Allocate immediate focus block for '{t.title}'.",
                        source_id=t.id,
                    )
                )

    # 2. Attention from Goals (Behind target or active bottleneck)
    behind_goals = (
        db.query(Goal)
        .filter(
            Goal.user_id == user.id,
            Goal.status == "BEHIND",
        )
        .all()
    )

    for g in behind_goals:
        score = compute_attention_score(
            urgency=0.8,
            impact=0.9 if g.area == LifeArea.STARTUP.value else 0.7,
            domain=g.area,
        )
        items.append(
            AttentionItem(
                id=f"att_goal_behind_{g.id}",
                type=AttentionItemType.STARTUP_TARGET_BEHIND.value
                if g.area == LifeArea.STARTUP.value
                else AttentionItemType.MISSED_GOAL.value,
                domain=g.area,
                title=f"Goal Behind Target: {g.name}",
                description=(
                    f"{g.area} milestone is behind expected pace "
                    f"({g.progress_fraction * 100:.0f}% achieved)."
                ),
                score=score,
                urgency=0.8,
                impact=0.9 if g.area == LifeArea.STARTUP.value else 0.7,
                suggested_action=f"Review tasks linked to '{g.name}' and schedule sprint.",
                source_id=g.id,
            )
        )

    # 3. Attention from Cross-Domain Signals (e.g. founder replies, inbound opportunities)
    if signals:
        for s in signals:
            if s.signal_type == SignalType.OPPORTUNITY_INBOUND.value:
                score = compute_attention_score(
                    urgency=s.urgency,
                    impact=s.importance,
                    domain=s.domain,
                )
                items.append(
                    AttentionItem(
                        id=f"att_signal_{s.domain}_{s.signal_type}_{s.title[:15].strip()}",
                        type=AttentionItemType.UNANSWERED_IMPORTANT_SIGNAL.value,
                        domain=s.domain,
                        title=f"High-Value Opportunity: {s.title}",
                        description=s.summary or s.title,
                        score=score,
                        urgency=s.urgency,
                        impact=s.importance,
                        provenance=s.provenance,
                        suggested_action="Respond or schedule demo call promptly.",
                        source_id=s.id,
                    )
                )

    # Sort descending by attention score
    items.sort(key=lambda x: x.score, reverse=True)
    return items
