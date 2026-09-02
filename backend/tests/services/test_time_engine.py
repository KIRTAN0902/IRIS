"""Available-time engine tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.calendar_event import CalendarEvent
from app.models.time_block import TimeBlock
from app.services import time_engine
from tests.conftest import utcnow


def test_empty_window_is_all_free(db, user_id):
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    avail = time_engine.compute_availability(
        db, user_id, window_start=now, window_end=now + timedelta(hours=4)
    )
    assert avail.total_free_minutes == 240
    assert len(avail.free_intervals) == 1


def test_calendar_events_and_blocks_are_subtracted(db: Session, user_id):
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    db.add(
        CalendarEvent(
            user_id=user_id,
            title="Lecture",
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
        )
    )
    db.add(
        TimeBlock(
            user_id=user_id,
            start_time=now + timedelta(hours=3),
            end_time=now + timedelta(hours=3, minutes=30),
            type="FOCUS",
            status="SCHEDULED",
        )
    )
    db.commit()

    avail = time_engine.compute_availability(
        db, user_id, window_start=now, window_end=now + timedelta(hours=4)
    )
    assert avail.total_free_minutes == 150
    # free: [start,+1h] and [+2h,+3h] and [+3h30,+4h]
    assert len(avail.free_intervals) == 3


def test_overlapping_busy_items_merge(db, user_id):
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    db.add(
        CalendarEvent(
            user_id=user_id,
            title="A",
            start_time=now,
            end_time=now + timedelta(minutes=90),
        )
    )
    db.add(
        CalendarEvent(
            user_id=user_id,
            title="B (overlaps A)",
            start_time=now + timedelta(minutes=60),
            end_time=now + timedelta(minutes=120),
        )
    )
    db.commit()

    avail = time_engine.compute_availability(
        db, user_id, window_start=now, window_end=now + timedelta(hours=2)
    )
    assert avail.total_free_minutes == 0
    assert len(avail.busy_intervals) == 1  # merged into one


def test_cancelled_blocks_do_not_count_as_busy(db, user_id):
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    db.add(
        TimeBlock(
            user_id=user_id,
            start_time=now,
            end_time=now + timedelta(hours=1),
            type="FOCUS",
            status="CANCELLED",
        )
    )
    db.commit()

    avail = time_engine.compute_availability(
        db, user_id, window_start=now, window_end=now + timedelta(hours=1)
    )
    assert avail.total_free_minutes == 60


def test_what_fits_picks_first_sufficient_slot(db, user_id):
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    avail = time_engine.compute_availability(
        db, user_id, window_start=now, window_end=now + timedelta(hours=3)
    )
    slot = time_engine.what_fits(avail, 120)
    assert slot is not None and slot.minutes >= 120
    assert time_engine.what_fits(avail, 300) is None


def test_invalid_window_raises(db, user_id):
    now = utcnow()
    with pytest.raises(ValueError):
        time_engine.compute_availability(db, user_id, window_start=now, window_end=now)
