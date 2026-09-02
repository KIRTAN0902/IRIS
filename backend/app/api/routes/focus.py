"""Focus session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.core.errors import ConflictError, NotFoundError
from app.models.enums import FocusStatus
from app.models.focus_session import FocusSession
from app.models.user import User
from app.schemas.common import FocusCompleteIn, FocusSessionOut, FocusStartIn
from app.utils.datetime import utcnow

router = APIRouter(prefix="/focus", tags=["focus"])


@router.post("/start", response_model=FocusSessionOut, status_code=201)
def start_focus(
    data: FocusStartIn | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    payload = data or FocusStartIn()
    if payload.task_id is not None:
        from app.services.task_service import get_task

        get_task(db, user.id, payload.task_id)  # ownership check
    running = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == user.id, FocusSession.status == FocusStatus.RUNNING.value)
        .first()
    )
    if running:
        raise ConflictError("A focus session is already running.", code="FOCUS_ALREADY_RUNNING")
    session = FocusSession(
        user_id=user.id,
        task_id=payload.task_id,
        planned_duration=payload.planned_duration,
        notes=payload.notes,
        started_at=utcnow(),
        status=FocusStatus.RUNNING.value,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/complete", response_model=FocusSessionOut)
def complete_focus(
    session_id: int,
    data: FocusCompleteIn | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    payload = data or FocusCompleteIn()
    session = (
        db.query(FocusSession)
        .filter(FocusSession.id == session_id, FocusSession.user_id == user.id)
        .first()
    )
    if not session:
        raise NotFoundError("Focus session not found.", code="FOCUS_NOT_FOUND")
    if session.status != FocusStatus.RUNNING.value:
        raise ConflictError("Focus session already finished.", code="FOCUS_ALREADY_FINISHED")

    now = utcnow()
    session.ended_at = now
    session.status = payload.status.value
    session.actual_duration = max(0, int((now - session.started_at).total_seconds() // 60))
    if payload.notes:
        session.notes = payload.notes

    # Feed actual duration back into the task (learning planned vs actual).
    if session.task_id and payload.status in (FocusStatus.COMPLETED, FocusStatus.PARTIAL):
        from app.models.task import Task

        task = db.query(Task).filter(Task.id == session.task_id).first()
        if task:
            add_minutes = session.actual_duration or 0
            task.actual_duration = (task.actual_duration or 0) + add_minutes

    db.commit()
    db.refresh(session)
    return session


@router.get("", response_model=list[FocusSessionOut])
def list_focus_sessions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == user.id)
        .order_by(FocusSession.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [FocusSessionOut.model_validate(s) for s in rows]
