"""Available-time engine.

Answers: "How much free time do I have in this window?" by subtracting
calendar events and active time blocks from the requested window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.calendar_event import CalendarEvent
from app.models.enums import TimeBlockStatus
from app.models.time_block import TimeBlock
from app.services import schedule_service


@dataclass
class FreeInterval:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return max(0, int((self.end - self.start).total_seconds() // 60))


@dataclass
class AvailabilityResult:
    window_start: datetime
    window_end: datetime
    busy_intervals: list[FreeInterval] = field(default_factory=list)
    free_intervals: list[FreeInterval] = field(default_factory=list)

    @property
    def total_free_minutes(self) -> int:
        return sum(i.minutes for i in self.free_intervals)

    @property
    def longest_free_interval(self) -> FreeInterval | None:
        return max(self.free_intervals, key=lambda i: i.minutes, default=None)


def _merge(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def compute_availability(
    db: Session,
    user_id: int,
    *,
    window_start: datetime,
    window_end: datetime,
) -> AvailabilityResult:
    """window_start must be <= window_end; both naive UTC."""
    if window_end <= window_start:
        raise ValueError("window_end must be after window_start")

    events: list[CalendarEvent] = schedule_service.list_calendar_events(
        db, user_id, start=window_start, end=window_end
    )
    blocks: list[TimeBlock] = schedule_service.list_time_blocks(
        db, user_id, start=window_start, end=window_end
    )

    busy_raw: list[tuple[datetime, datetime]] = [(e.start_time, e.end_time) for e in events]
    busy_raw += [
        (b.start_time, b.end_time) for b in blocks if b.status != TimeBlockStatus.CANCELLED.value
    ]

    # Clamp everything to the window.
    clamped = [(max(s, window_start), min(e, window_end)) for s, e in busy_raw]
    clamped = [(s, e) for s, e in clamped if s < e]

    result = AvailabilityResult(window_start=window_start, window_end=window_end)
    result.busy_intervals = [FreeInterval(s, e) for s, e in _merge(clamped)]

    cursor = window_start
    free: list[FreeInterval] = []
    for s, e in _merge(clamped):
        if cursor < s:
            free.append(FreeInterval(cursor, s))
        cursor = max(cursor, e)
    if cursor < window_end:
        free.append(FreeInterval(cursor, window_end))
    result.free_intervals = free
    return result


def what_fits(avail: AvailabilityResult, needed_minutes: int) -> FreeInterval | None:
    """First free interval that fits `needed_minutes` (smallest sufficient first)."""
    fitting = sorted(
        (i for i in avail.free_intervals if i.minutes >= needed_minutes),
        key=lambda i: i.start,
    )
    return fitting[0] if fitting else None


def next_free_slot(
    db: Session,
    user_id: int,
    *,
    needed_minutes: int,
    search_days: int = 7,
    from_dt: datetime | None = None,
) -> FreeInterval | None:
    """Search forward for the first slot that fits."""
    from app.utils.datetime import utcnow

    start = (from_dt or utcnow()).replace(minute=0, second=0, microsecond=0)
    horizon = start + timedelta(days=search_days)
    day_step = timedelta(days=1)
    cursor_day = start
    while cursor_day < horizon:
        avail = compute_availability(
            db,
            user_id,
            window_start=cursor_day,
            window_end=min(cursor_day + day_step, horizon),
        )
        slot = what_fits(avail, needed_minutes)
        if slot:
            return slot
        cursor_day += day_step
    return None
