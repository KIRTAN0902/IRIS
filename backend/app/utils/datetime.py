"""Datetime helpers.

Convention: datetimes are stored **naive UTC** in the database. Convert to a
user's local timezone only at boundaries (analytics day-buckets, reviews).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    """Naive UTC 'now' -- the canonical clock for all persistence."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_local(dt: datetime, tz_name: str) -> datetime:
    return dt.replace(tzinfo=UTC).astimezone(ZoneInfo(tz_name))


def from_local(d: date | datetime, tz_name: str, *, end_of_day: bool = False) -> datetime:
    """Convert a naive local date/datetime into naive UTC."""
    if isinstance(d, date) and not isinstance(d, datetime):
        t = time.max if end_of_day else time.min
        d = datetime.combine(d, t)
    return d.replace(tzinfo=ZoneInfo(tz_name)).astimezone(UTC).replace(tzinfo=None)


def localize_date_boundaries(day: date, tz_name: str) -> tuple[datetime, datetime]:
    """UTC [start, end) for a calendar day in the given timezone."""
    start = from_local(day, tz_name)
    end = from_local(day + timedelta(days=1), tz_name)
    return start, end


def minutes_between(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() // 60))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
