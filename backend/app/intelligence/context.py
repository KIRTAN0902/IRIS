"""Structured Decision Context Builder.

Builds snapshot-based decision context incorporating:
1. Facts (Objective information about the user, routine, college, internship, startup)
2. Preferences (How the user wants IRIS to prioritize: primary startup goal, meaningful progress)
3. Goals (Hierarchical goals, progress, active bottlenecks)
4. Current State (Impending deadlines, overdue items, startup pipeline, available time)
5. Constraints (Hard sleep time, routine, fixed commitments, recurring schedules)
6. Resources (Time, energy, attention)
7. Candidate Tasks (Ranked deterministically with score breakdowns)
8. Historical Signals (Past week completion patterns, focus minutes)

Output is 100% JSON-serializable. No SQLAlchemy objects leak into the AI reasoning layer.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence.constraint_engine import evaluate_constraints
from app.intelligence.goal_engine import analyze_goals
from app.intelligence.priority_engine import PriorityBreakdown, breakdown_to_dict, rank_tasks
from app.models.enums import TaskPriority, TaskStatus
from app.models.recurring_schedule import RecurringSchedule
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskOut
from app.services import analytics_service, time_engine
from app.services.memory_service import memory_service
from app.utils.datetime import minutes_between, to_local, utcnow



class ContextProvider(Protocol):
    """Protocol for modular context providers."""

    def provide_context(self, db: Session, user: User, **kwargs) -> dict[str, Any]: ...


class FactProvider:
    """Provides objective facts from user profile and defaults."""

    def provide_context(self, user: User) -> dict[str, Any]:
        default_facts = {
            "wake_time": "06:00",
            "sleep_time": "23:00",
            "college": {
                "degree": "B.Tech AI & ML",
                "semester": "4th semester",
                "subjects": [
                    "Agentic AI",
                    "Compiler Design",
                    "Software Project Management",
                    "DSA (MOOC)",
                ],
                "pending_assignments_count": 0,
            },
            "internship": {
                "schedule": "Monday–Friday, 11:00 AM – 8:00 PM",
                "fixed_hours_start": "11:00",
                "fixed_hours_end": "20:00",
            },
            "startup": {
                "name": "MARKETORY",
                "product": "NEXUS",
                "stage": "Pre-revenue / early validation",
                "target_audience": "Digital marketing and performance marketing agencies",
                "current_bottleneck": "Customer validation + distribution",
                "current_objective": "Founder acquisition and outreach",
                "strategy": "Founder-led outbound + LinkedIn content",
                "validation_approach": "Talk → Observe → Test → Iterate → Validate",
            },
        }
        from app.intelligence.profile_facts import normalize_facts

        user_facts = dict(default_facts)
        user_facts.update(normalize_facts(user.facts))
        return user_facts


class PreferenceProvider:
    """Provides user operating preferences."""

    def provide_context(self, user: User) -> dict[str, Any]:
        default_preferences = {
            "primary_long_term_goal": "STARTUP",
            "startup_time_allocation": "as_much_as_reasonably_possible",
            "optimization_objective": "meaningful_progress_over_busywork",
            "schedule_sustainability": "sustainable_without_artificial_filler",
            "hard_constraints_must_win": True,
        }
        user_prefs = dict(default_preferences)
        if user.preferences:
            user_prefs.update(user.preferences)
        return user_prefs


def _serialize_ranked_task(pair: tuple[Task, PriorityBreakdown]) -> dict[str, Any]:
    task, bd = pair
    return {
        "task": TaskOut.model_validate(task).model_dump(mode="json"),
        "priority_score": bd.total,
        "breakdown": {**breakdown_to_dict(bd), "notes": bd.notes},
    }


class DecisionContextBuilder:
    """Assembles the full structured decision context."""

    def __init__(self):
        self.fact_provider = FactProvider()
        self.pref_provider = PreferenceProvider()

    def build(
        self,
        db: Session,
        user: User,
        *,
        available_minutes: int | None = None,
        window_start=None,
        window_end=None,
        current_energy: str | None = None,
    ) -> dict[str, Any]:
        now_utc = utcnow()
        now_local = to_local(now_utc, user.timezone)

        # 1. Facts & Preferences
        facts = self.fact_provider.provide_context(user)
        preferences = self.pref_provider.provide_context(user)

        # 2. Query Recurring Schedules
        recurring_schedules = (
            db.query(RecurringSchedule)
            .filter(
                RecurringSchedule.user_id == user.id,
                RecurringSchedule.status == "ACTIVE",
            )
            .all()
        )

        # 3. Evaluate Constraints
        constraint_eval = evaluate_constraints(
            facts,
            now_local,
            recurring_schedules=recurring_schedules,
        )

        # 4. Availability & Free intervals
        start = window_start or now_utc
        end = window_end or (start + timedelta(hours=4))

        avail = time_engine.compute_availability(db, user.id, window_start=start, window_end=end)
        total_free_minutes = avail.total_free_minutes

        if available_minutes is None:
            if total_free_minutes > 0:
                available_minutes = total_free_minutes
            elif constraint_eval.minutes_until_next_constraint:
                available_minutes = max(15, constraint_eval.minutes_until_next_constraint)
            else:
                available_minutes = 90

            # Hard clamp: if sleep is imminent, cannot exceed minutes until sleep
            mins_left = constraint_eval.minutes_until_next_constraint
            if mins_left is not None and mins_left > 0:
                available_minutes = min(available_minutes, mins_left)

        free_intervals = [
            {"start": i.start.isoformat(), "end": i.end.isoformat(), "minutes": i.minutes}
            for i in avail.free_intervals
        ]

        # 5. Goals & Bottlenecks
        goals_data = analyze_goals(db, user.id)

        # 6. Open Tasks & Deterministic Priority Ranking
        open_tasks = (
            db.query(Task)
            .filter(
                Task.user_id == user.id,
                Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]),
            )
            .all()
        )

        ranked = rank_tasks(
            db,
            open_tasks[: settings.ai_context_max_tasks * 4],
            available_minutes=available_minutes,
            current_energy=current_energy,
            now=now_utc,
        )

        serialized_tasks = [
            _serialize_ranked_task(pair) for pair in ranked[: settings.ai_context_max_tasks]
        ]

        # 7. Urgent obligations detection (deadlines <= 24h or overdue or CRITICAL)
        urgent_obligations = []
        for t in open_tasks:
            is_urgent = False
            urgency_reason = ""
            if t.is_overdue:
                is_urgent = True
                urgency_reason = "Overdue"
            elif t.deadline:
                m = minutes_between(now_utc, t.deadline)
                if m <= 24 * 60:
                    is_urgent = True
                    urgency_reason = f"Due in {m // 60}h {m % 60}m"
            elif t.priority == TaskPriority.CRITICAL.value:
                is_urgent = True
                urgency_reason = "Critical Priority"

            if is_urgent:
                urgent_obligations.append(
                    {
                        "task_id": t.id,
                        "title": t.title,
                        "area": t.area,
                        "priority": t.priority,
                        "deadline_utc": t.deadline.isoformat() if t.deadline else None,
                        "estimated_duration": t.estimated_duration,
                        "reason": urgency_reason,
                    }
                )

        # 8. Startup Metrics & Pipeline
        startup_metrics = None
        try:
            sa = analytics_service.startup_analytics(db, user.id)
            startup_metrics = sa.model_dump()
        except Exception:
            startup_metrics = None

        # 9. Historical productivity signals
        productivity_week = None
        try:
            pw = analytics_service.productivity_analytics(
                db, user.id, period="week", tz_name=user.timezone
            )
            productivity_week = pw.model_dump()
        except Exception:
            productivity_week = None

        # 10. Cross-Domain Signals
        from app.intelligence.attention_engine import generate_attention_items
        from app.intelligence.signals import SignalQuery, signal_repo

        raw_signals = signal_repo.gather_all_signals(
            db, user, SignalQuery(user_id=user.id, now_utc=now_utc)
        )

        domain_signals: dict[str, list[dict[str, Any]]] = {}
        for s in raw_signals:
            dom_key = s.domain.lower()
            if dom_key not in domain_signals:
                domain_signals[dom_key] = []
            domain_signals[dom_key].append(
                {
                    "domain": s.domain,
                    "signal_type": s.signal_type,
                    "title": s.title,
                    "source": s.source,
                    "provenance": s.provenance,
                    "importance": s.importance,
                    "urgency": s.urgency,
                    "summary": s.summary,
                    "payload": s.payload,
                }
            )

        # 11. Attention Items (Deterministic scoring across all domains)
        attention_objects = generate_attention_items(db, user, signals=raw_signals, now_utc=now_utc)
        attention_items = [item.to_dict() for item in attention_objects]

        # 12. Persistent User Memories
        active_memories = memory_service.get_memories(db, user.id, is_active=True, limit=15)
        memories_data = [
            {
                "id": m.id,
                "category": m.category,
                "key": m.key,
                "content": m.content,
                "importance": m.importance,
            }
            for m in active_memories
        ]

        # Explicitly declare external domains that are currently not connected
        unavailable_domains = ["EMAIL", "FINANCE", "DOCUMENTS"]

        return {
            "current_time_utc": now_utc.isoformat(),
            "current_local_time": now_local.isoformat(),
            "user_timezone": user.timezone,
            "available_minutes": available_minutes,
            "current_energy": current_energy or "NORMAL",
            "facts": facts,
            "preferences": preferences,
            "memories": memories_data,
            "goals": goals_data,
            "urgent_obligations": urgent_obligations,

            "current_window": {
                "is_in_flexible_window": constraint_eval.is_in_flexible_window,
                "is_in_hard_constraint": constraint_eval.is_in_hard_constraint,
                "active_block_name": constraint_eval.active_constraint_name,
                "active_block_type": constraint_eval.active_block_type,
                "minutes_remaining_in_block": constraint_eval.minutes_remaining_in_block,
                "minutes_until_next_hard_constraint": constraint_eval.minutes_until_next_constraint,
                "next_hard_constraint_name": constraint_eval.next_constraint_name,
            },
            "fixed_constraints": {
                "hard_sleep_time": constraint_eval.hard_sleep_time,
                "hard_wake_time": constraint_eval.hard_wake_time,
                "is_in_hard_constraint": constraint_eval.is_in_hard_constraint,
                "active_constraint_name": constraint_eval.active_constraint_name,
                "minutes_until_next_constraint": constraint_eval.minutes_until_next_constraint,
                "next_constraint_name": constraint_eval.next_constraint_name,
                "fixed_commitments": constraint_eval.fixed_commitments,
            },
            "flexible_windows": constraint_eval.flexible_windows,
            "free_intervals_utc": free_intervals,
            "ranked_tasks": serialized_tasks,
            "startup_state": {
                "metrics": startup_metrics,
                "facts": facts.get("startup", {}),
                "bottlenecks": goals_data.get("identified_bottlenecks", []),
            },
            "historical_signals": {
                "productivity_week": productivity_week,
            },
            "domain_signals": domain_signals,
            "attention_items": attention_items,
            "unavailable_domains": unavailable_domains,
        }


# Singleton instance
context_builder_instance = DecisionContextBuilder()


def build_decision_context(
    db: Session,
    user: User,
    *,
    available_minutes: int | None = None,
    window_start=None,
    window_end=None,
    current_energy: str | None = None,
) -> dict[str, Any]:
    """Convenience function to build structured decision context."""
    return context_builder_instance.build(
        db,
        user,
        available_minutes=available_minutes,
        window_start=window_start,
        window_end=window_end,
        current_energy=current_energy,
    )
