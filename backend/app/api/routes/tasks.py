"""Task endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.task import TaskCompleteIn, TaskCreate, TaskOut, TaskUpdate
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut], summary="List tasks (filterable)")
def list_tasks(
    area: str | None = Query(None, description="COLLEGE|INTERNSHIP|STARTUP|PERSONAL"),
    task_status: str | None = Query(None, alias="status"),
    priority: str | None = None,
    goal_id: int | None = None,
    project_id: int | None = None,
    deadline_before: datetime | None = None,
    deadline_after: datetime | None = None,
    overdue_only: bool = False,
    open_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    items, _total = task_service.list_tasks(
        db,
        user.id,
        area=area,
        status=task_status,
        priority=priority,
        goal_id=goal_id,
        project_id=project_id,
        deadline_before=deadline_before,
        deadline_after=deadline_after,
        overdue_only=overdue_only,
        open_only=open_only,
        limit=limit,
        offset=offset,
    )
    return [TaskOut.model_validate(t) for t in items]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return TaskOut.model_validate(task_service.create_task(db, user.id, data))


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    t = task_service.get_task(db, user.id, task_id)
    return TaskOut.model_validate(t)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    data: TaskUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    t = task_service.update_task(db, user.id, task_id, data)
    return TaskOut.model_validate(t)


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(
    task_id: int,
    data: TaskCompleteIn | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    actual = data.actual_duration if data else None
    return TaskOut.model_validate(task_service.complete_task(db, user.id, task_id, actual))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    task_service.delete_task(db, user.id, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
