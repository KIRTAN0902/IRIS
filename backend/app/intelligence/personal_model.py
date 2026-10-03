"""Personal model: IRIS's long-term understanding of the user.

Two complementary sources:

- **Stated**: what the user has told IRIS (profile facts and preferences,
  recurring schedules, and memories about routine, work style, preferences,
  constraints and standing instructions).
- **Observed**: patterns learned from behaviour (when work actually gets
  done, best days, how estimates compare to reality, focus-session length and
  follow-through, area balance, throughput, self-rated productivity).

Observed patterns need a minimum number of samples and always carry their
sample size, so IRIS never presents a guess as a fact.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from statistics import median
from typing import Any

from sqlalchemy.orm import Session

from app.models.daily_review import DailyReview
from app.models.enums import FocusStatus, TaskStatus
from app.models.focus_session import FocusSession
from app.models.recurring_schedule import RecurringSchedule
from app.models.task import Task
from app.models.user import User
from app.utils.datetime import to_local, utcnow

# Memory categories that describe *who the user is* and are always in context.
PROFILE_CATEGORIES = ("INSTRUCTION", "CONSTRAINT", "ROUTINE", "WORK_STYLE", "PREFERENCE")

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MIN_ACTIVITY = 6
_MIN_DAYS = 7
_MIN_ESTIMATES = 4
_MIN_FOCUS = 3
_MIN_REVIEWS = 3


# --- Stated ------------------------------------------------------------------


def _compress_days(days: list[str]) -> str:
    idx = sorted({_WEEKDAYS.index(d) for d in days if d in _WEEKDAYS})
    if not idx:
        return "Daily"
    if idx == list(range(7)):
        return "Daily"
    if idx == list(range(5)):
        return "Mon-Fri"
    if idx == [5, 6]:
        return "Weekends"
    if len(idx) > 2 and idx == list(range(idx[0], idx[-1] + 1)):
        return f"{_WEEKDAYS[idx[0]]}-{_WEEKDAYS[idx[-1]]}"
    return ",".join(_WEEKDAYS[i] for i in idx)


def weekly_routine(db: Session, user_id: int) -> list[dict[str, Any]]:
    schedules = (
        db.query(RecurringSchedule)
        .filter(RecurringSchedule.user_id == user_id, RecurringSchedule.status == "ACTIVE")
        .order_by(RecurringSchedule.start_time)
        .all()
    )
    return [
        {
            "days": _compress_days(
                [d.strip()[:3].title() for d in (s.days_of_week or "").split(",") if d.strip()]
            ),
            "start": s.start_time,
            "end": s.end_time,
            "name": s.name,
            "type": s.type,
            "hard": bool(s.is_hard_constraint),
        }
        for s in schedules
    ]


def _stated_memories(db: Session, user_id: int, limit: int) -> list[dict[str, Any]]:
    from app.models.ai_memory import AIMemory

    rows = (
        db.query(AIMemory)
        .filter(
            AIMemory.user_id == user_id,
            AIMemory.is_active.is_(True),
            AIMemory.category.in_(PROFILE_CATEGORIES),
        )
        .order_by(AIMemory.importance.desc(), AIMemory.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [{"id": m.id, "category": m.category, "key": m.key, "content": m.content} for m in rows]


# --- Observed ---------------------------------------------------------------


def _best_window(hours: Counter, width: int = 3) -> tuple[int, int, int]:
    """Best circular window of ``width`` hours: (start_hour, events, total)."""
    total = sum(hours.values())
    best_start, best = 0, -1
    for start in range(24):
        count = sum(hours.get((start + k) % 24, 0) for k in range(width))
        if count > best:
            best_start, best = start, count
    return best_start, best, total


def observe_work_patterns(db: Session, user: User, lookback_days: int = 45) -> dict[str, Any]:
    tz = user.timezone
    since = utcnow() - timedelta(days=lookback_days)

    completed = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.status == TaskStatus.COMPLETED.value,
            Task.completed_at.isnot(None),
            Task.completed_at >= since,
        )
        .all()
    )
    sessions = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == user.id, FocusSession.started_at >= since)
        .all()
    )
    reviews = (
        db.query(DailyReview)
        .filter(DailyReview.user_id == user.id, DailyReview.date >= since.date())
        .order_by(DailyReview.date.desc())
        .all()
    )

    patterns: dict[str, Any] = {"lookback_days": lookback_days}

    # When does work happen? Completions + focus-session starts, in local time.
    activity = [to_local(t.completed_at, tz) for t in completed] + [
        to_local(s.started_at, tz) for s in sessions if s.status != FocusStatus.RUNNING.value
    ]
    if len(activity) >= _MIN_ACTIVITY:
        hours = Counter(a.hour for a in activity)
        start, count, total = _best_window(hours)
        sorted_hours = sorted(a.hour + a.minute / 60 for a in activity)
        p10 = sorted_hours[int(len(sorted_hours) * 0.1)]
        p90 = sorted_hours[min(len(sorted_hours) - 1, int(len(sorted_hours) * 0.9))]
        patterns["peak_hours"] = {
            "window": f"{start:02d}:00-{(start + 3) % 24:02d}:00",
            "share_pct": round(100 * count / total),
            "samples": total,
        }
        patterns["active_span"] = {
            "from": f"{int(p10):02d}:00",
            "to": f"{int(p90) % 24:02d}:00",
            "samples": total,
        }

    # Which days are productive?
    if len(completed) >= _MIN_DAYS:
        days = Counter(to_local(t.completed_at, tz).weekday() for t in completed)
        ranked = [d for d, _ in days.most_common()]
        patterns["best_days"] = {
            "days": [_WEEKDAYS[d] for d in ranked[:2]],
            "quietest": _WEEKDAYS[ranked[-1]] if len(ranked) > 2 else None,
            "samples": len(completed),
        }
        weeks = max(1.0, lookback_days / 7)
        patterns["throughput"] = {
            "tasks_per_week": round(len(completed) / weeks, 1),
            "samples": len(completed),
        }
        areas = Counter(t.area for t in completed)
        patterns["area_mix_pct"] = {
            a: round(100 * c / len(completed)) for a, c in areas.most_common()
        }

    # Estimation accuracy.
    ratios = [
        t.actual_duration / t.estimated_duration
        for t in completed
        if t.actual_duration and t.estimated_duration and t.estimated_duration > 0
    ]
    if len(ratios) >= _MIN_ESTIMATES:
        r = median(ratios)
        if r > 1.15:
            verdict = f"tasks usually take ~{round((r - 1) * 100)}% longer than estimated"
        elif r < 0.85:
            verdict = f"tasks usually finish ~{round((1 - r) * 100)}% faster than estimated"
        else:
            verdict = "estimates are usually accurate"
        patterns["estimation"] = {"ratio": round(r, 2), "verdict": verdict, "samples": len(ratios)}

    # Focus sessions.
    finished = [s for s in sessions if s.status != FocusStatus.RUNNING.value]
    if len(finished) >= _MIN_FOCUS:
        lengths = [s.actual_duration for s in finished if s.actual_duration]
        done = sum(1 for s in finished if s.status == FocusStatus.COMPLETED.value)
        patterns["focus"] = {
            "typical_minutes": round(median(lengths)) if lengths else None,
            "completion_rate_pct": round(100 * done / len(finished)),
            "samples": len(finished),
        }

    # Self-reported productivity.
    rated = [r.productivity_rating for r in reviews if r.productivity_rating]
    if len(rated) >= _MIN_REVIEWS:
        patterns["self_rating"] = {
            "average": round(sum(rated) / len(rated), 1),
            "samples": len(rated),
            "latest_blocker": next((r.blockers for r in reviews if r.blockers), None),
        }

    return patterns


# --- Assembly & rendering -------------------------------------------------------------


def build_personal_model(
    db: Session, user: User, *, memory_limit: int = 25, lookback_days: int = 45
) -> dict[str, Any]:
    from app.intelligence.context import FactProvider, PreferenceProvider

    return {
        "name": user.name,
        "timezone": user.timezone,
        "facts": FactProvider().provide_context(user),
        "preferences": PreferenceProvider().provide_context(user),
        "weekly_routine": weekly_routine(db, user.id),
        "stated": _stated_memories(db, user.id, memory_limit),
        "observed": observe_work_patterns(db, user, lookback_days),
    }


def _flatten(value: Any, limit: int = 220) -> str:
    if isinstance(value, dict):
        text = "; ".join(
            f"{k}={_flatten(v, 80)}" for k, v in value.items() if v not in (None, "", [])
        )
    elif isinstance(value, list):
        text = ", ".join(_flatten(v, 60) for v in value)
    else:
        text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def render_personal_model(pm: dict[str, Any], detail: str = "standard") -> str:
    lines = [f"WHO {pm['name'].upper()} IS (personal model; stated + observed):"]

    facts = pm.get("facts") or {}
    has_routine = bool(pm.get("weekly_routine"))
    fact_limit = 220 if detail == "compact" else 480
    if facts:
        lines.append("Profile:")
        seen_values: set[str] = set()
        for k, v in facts.items():
            if v in (None, "", [], {}):
                continue
            # The structured weekly routine below already covers schedule-like facts.
            if has_routine and isinstance(v, list) and any(w in k for w in ("routine", "schedule")):
                continue
            rendered = _flatten(v, fact_limit)
            if rendered in seen_values:  # e.g. "wake" duplicating "wake_time"
                continue
            seen_values.add(rendered)
            lines.append(f"- {k.replace('_', ' ')}: {rendered}")

    prefs = pm.get("preferences") or {}
    if prefs:
        lines.append(
            "Operating preferences: "
            + _flatten({k: v for k, v in prefs.items() if not isinstance(v, dict)}, 400)
        )

    if pm.get("weekly_routine"):
        lines.append("Weekly routine:")
        for r in pm["weekly_routine"]:
            hard = " [hard]" if r["hard"] else ""
            lines.append(f"- {r['days']} {r['start']}-{r['end']} {r['name']}{hard}")

    if pm.get("stated"):
        lines.append("What they told IRIS (honour these):")
        cap = {"compact": 10, "standard": 18, "full": 30}.get(detail, 18)
        for m in pm["stated"][:cap]:
            lines.append(f"- [{m['category']}] {m['content']}")

    obs = pm.get("observed") or {}
    observed_lines = []
    if "peak_hours" in obs:
        p = obs["peak_hours"]
        observed_lines.append(
            f"- Gets the most done {p['window']} ({p['share_pct']}% of {p['samples']} work events)"
        )
    if "active_span" in obs:
        a = obs["active_span"]
        observed_lines.append(f"- Typically works between {a['from']} and {a['to']}")
    if "best_days" in obs:
        b = obs["best_days"]
        quiet = f"; quietest {b['quietest']}" if b.get("quietest") else ""
        observed_lines.append(f"- Most productive days: {', '.join(b['days'])}{quiet}")
    if "throughput" in obs:
        observed_lines.append(f"- Completes ~{obs['throughput']['tasks_per_week']} tasks/week")
    if "area_mix_pct" in obs:
        mix = ", ".join(f"{k} {v}%" for k, v in obs["area_mix_pct"].items())
        observed_lines.append(f"- Completed work by area: {mix}")
    if "estimation" in obs:
        e = obs["estimation"]
        observed_lines.append(f"- Estimation: {e['verdict']} (n={e['samples']})")
    if "focus" in obs:
        f = obs["focus"]
        typical = f"~{f['typical_minutes']}m sessions, " if f.get("typical_minutes") else ""
        observed_lines.append(
            f"- Focus: {typical}{f['completion_rate_pct']}% completed (n={f['samples']})"
        )
    if "self_rating" in obs:
        s = obs["self_rating"]
        blocker = f"; latest blocker: {s['latest_blocker']}" if s.get("latest_blocker") else ""
        observed_lines.append(f"- Self-rated productivity {s['average']}/5{blocker}")

    if observed_lines:
        lines.append(f"Observed from the last {obs.get('lookback_days', 45)} days of behaviour:")
        lines.extend(observed_lines)
    else:
        lines.append("Observed patterns: not enough history yet (they appear as work gets logged).")

    return "\n".join(lines)
