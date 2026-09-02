"""Schedule endpoints: time blocks + calendar events + free-time queries."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.time_block import (
    CalendarEventCreate,
    CalendarEventOut,
    TimeBlockCreate,
    TimeBlockOut,
    TimeBlockUpdate,
)
from app.services import schedule_service, time_engine
from app.utils.datetime import utcnow

router = APIRouter(tags=["schedule"])


# --- Time blocks ---------------------------------------------------------------


@router.get("/time-blocks", response_model=list[TimeBlockOut])
def list_time_blocks(
    start: datetime | None = None,
    end: datetime | None = None,
    task_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return [
        TimeBlockOut.model_validate(b)
        for b in schedule_service.list_time_blocks(
            db, user.id, start=start, end=end, task_id=task_id
        )
    ]


@router.post("/time-blocks", response_model=TimeBlockOut, status_code=status.HTTP_201_CREATED)
def create_time_block(
    data: TimeBlockCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return TimeBlockOut.model_validate(schedule_service.create_time_block(db, user.id, data))


@router.patch("/time-blocks/{block_id}", response_model=TimeBlockOut)
def update_time_block(
    block_id: int,
    data: TimeBlockUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return TimeBlockOut.model_validate(
        schedule_service.update_time_block(db, user.id, block_id, data)
    )


@router.delete("/time-blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_block(
    block_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    schedule_service.delete_time_block(db, user.id, block_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Calendar events ------------------------------------------------------------


@router.get("/calendar-events", response_model=list[CalendarEventOut])
def list_calendar_events(
    start: datetime | None = None,
    end: datetime | None = None,
    source: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return [
        CalendarEventOut.model_validate(e)
        for e in schedule_service.list_calendar_events(
            db, user.id, start=start, end=end, source=source
        )
    ]


@router.post(
    "/calendar-events", response_model=CalendarEventOut, status_code=status.HTTP_201_CREATED
)
def create_calendar_event(
    data: CalendarEventCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return CalendarEventOut.model_validate(
        schedule_service.create_calendar_event(db, user.id, data)
    )


# --- Availability ---------------------------------------------------------------


@router.get("/availability", summary="Free time within a window")
def availability(
    window_start: datetime | None = Query(None),
    window_end: datetime | None = Query(None),
    hours_ahead: float | None = Query(
        None, gt=0, le=72, description="Alternative to explicit window"
    ),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from datetime import timedelta

    now = utcnow()
    start = window_start or now
    end = window_end or (start + timedelta(hours=hours_ahead or 12))
    result = time_engine.compute_availability(db, user.id, window_start=start, window_end=end)
    return {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "total_free_minutes": result.total_free_minutes,
        "free_intervals": [
            {"start": i.start.isoformat(), "end": i.end.isoformat(), "minutes": i.minutes}
            for i in result.free_intervals
        ],
        "busy_intervals": [
            {"start": i.start.isoformat(), "end": i.end.isoformat(), "minutes": i.minutes}
            for i in result.busy_intervals
        ],
    }
