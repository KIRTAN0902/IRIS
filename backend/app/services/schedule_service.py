"""Schedule service -- time blocks, calendar events, overlap detection."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.calendar_event import CalendarEvent
from app.models.enums import TimeBlockStatus
from app.models.time_block import TimeBlock
from app.schemas.time_block import CalendarEventCreate, TimeBlockCreate, TimeBlockUpdate

# --- Time blocks ---------------------------------------------------------------


def list_time_blocks(
    db: Session,
    user_id: int,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    task_id: int | None = None,
) -> list[TimeBlock]:
    q = db.query(TimeBlock).filter(TimeBlock.user_id == user_id)
    if start:
        q = q.filter(TimeBlock.end_time > start)
    if end:
        q = q.filter(TimeBlock.start_time < end)
    if task_id:
        q = q.filter(TimeBlock.task_id == task_id)
    return q.order_by(TimeBlock.start_time.asc()).all()


def create_time_block(db: Session, user_id: int, data: TimeBlockCreate) -> TimeBlock:
    payload = data.model_dump()
    allow_overlap = payload.pop("allow_overlap", False)
    if not allow_overlap:
        conflicts = find_overlapping_blocks(db, user_id, data.start_time, data.end_time)
        if conflicts:
            raise ConflictError("Time block overlaps an existing block.", code="TIME_BLOCK_OVERLAP")
    block = TimeBlock(user_id=user_id, **payload)
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


def get_time_block(db: Session, user_id: int, block_id: int) -> TimeBlock:
    block = (
        db.query(TimeBlock).filter(TimeBlock.id == block_id, TimeBlock.user_id == user_id).first()
    )
    if not block:
        raise NotFoundError("Time block not found.", code="TIME_BLOCK_NOT_FOUND")
    return block


def update_time_block(db: Session, user_id: int, block_id: int, data: TimeBlockUpdate) -> TimeBlock:
    block = get_time_block(db, user_id, block_id)
    updates = data.model_dump(exclude_unset=True)
    new_start = updates.get("start_time", block.start_time)
    new_end = updates.get("end_time", block.end_time)
    if new_end <= new_start:
        raise ConflictError("end_time must be after start_time.", code="VALIDATION_ERROR")
    conflicts = find_overlapping_blocks(db, user_id, new_start, new_end, exclude_id=block_id)
    allow = updates.pop("allow_overlap", False)
    if conflicts and not allow:
        raise ConflictError("Time block overlaps an existing block.", code="TIME_BLOCK_OVERLAP")
    for key, value in updates.items():
        setattr(block, key, value)
    db.commit()
    db.refresh(block)
    return block


def delete_time_block(db: Session, user_id: int, block_id: int) -> None:
    block = get_time_block(db, user_id, block_id)
    db.delete(block)
    db.commit()


def find_overlapping_blocks(
    db: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    *,
    exclude_id: int | None = None,
) -> list[TimeBlock]:
    """Blocks that conflict with [start, end), excluding cancelled ones."""
    q = db.query(TimeBlock).filter(
        TimeBlock.user_id == user_id,
        TimeBlock.status != TimeBlockStatus.CANCELLED.value,
        TimeBlock.start_time < end,
        TimeBlock.end_time > start,
    )
    if exclude_id:
        q = q.filter(TimeBlock.id != exclude_id)
    return q.all()


# --- Calendar events ------------------------------------------------------------


def list_calendar_events(
    db: Session,
    user_id: int,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    source: str | None = None,
) -> list[CalendarEvent]:
    q = db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id)
    if start:
        q = q.filter(CalendarEvent.end_time > start)
    if end:
        q = q.filter(CalendarEvent.start_time < end)
    if source:
        q = q.filter(CalendarEvent.source == source)
    return q.order_by(CalendarEvent.start_time.asc()).all()


def create_calendar_event(db: Session, user_id: int, data: CalendarEventCreate) -> CalendarEvent:
    event = CalendarEvent(user_id=user_id, **data.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
