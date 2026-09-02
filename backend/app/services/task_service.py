"""Task service -- all task business logic lives here."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func as safunc
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.enums import TaskStatus
from app.models.task import Task
from app.models.time_block import TimeBlock
from app.schemas.task import TaskCreate, TaskUpdate
from app.utils.datetime import utcnow


def list_tasks(
    db: Session,
    user_id: int,
    *,
    area: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    goal_id: int | None = None,
    project_id: int | None = None,
    deadline_before: datetime | None = None,
    deadline_after: datetime | None = None,
    overdue_only: bool = False,
    open_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Task], int]:
    q = db.query(Task).filter(Task.user_id == user_id)
    if area:
        q = q.filter(Task.area == area)
    if status:
        q = q.filter(Task.status == status)
    if priority:
        q = q.filter(Task.priority == priority)
    if goal_id:
        q = q.filter(Task.goal_id == goal_id)
    if project_id:
        q = q.filter(Task.project_id == project_id)
    if deadline_before:
        q = q.filter(Task.deadline <= deadline_before)
    if deadline_after:
        q = q.filter(Task.deadline >= deadline_after)
    if open_only:
        q = q.filter(Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]))
    if overdue_only:
        now = utcnow()
        q = q.filter(
            Task.deadline.is_not(None),
            Task.deadline < now,
            Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]),
        )
    total = q.count()
    # Soonest deadline first (open-ended tasks last), then newest.
    items = (
        q.order_by(Task.deadline.asc().nulls_last(), Task.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return items, total


def _validate_refs(
    db: Session, user_id: int, *, goal_id: int | None, project_id: int | None
) -> None:
    from app.models.goal import Goal
    from app.models.project import Project

    if goal_id is not None:
        goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user_id).first()
        if not goal:
            raise NotFoundError(f"Goal {goal_id} not found.", code="GOAL_NOT_FOUND")
    if project_id is not None:
        project = (
            db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
        )
        if not project:
            raise NotFoundError(f"Project {project_id} not found.", code="PROJECT_NOT_FOUND")


def create_task(db: Session, user_id: int, data: TaskCreate) -> Task:
    _validate_refs(db, user_id, goal_id=data.goal_id, project_id=data.project_id)
    task = Task(user_id=user_id, **data.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, user_id: int, task_id: int) -> Task:
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise NotFoundError("Task not found.", code="TASK_NOT_FOUND")
    return task


def update_task(db: Session, user_id: int, task_id: int, data: TaskUpdate) -> Task:
    task = get_task(db, user_id, task_id)
    updates = data.model_dump(exclude_unset=True)
    _validate_refs(
        db,
        user_id,
        goal_id=updates.get("goal_id", task.goal_id),
        project_id=updates.get("project_id", task.project_id),
    )
    for key, value in updates.items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, user_id: int, task_id: int) -> None:
    task = get_task(db, user_id, task_id)
    active_block = (
        db.query(TimeBlock)
        .filter(TimeBlock.task_id == task_id, TimeBlock.status == "SCHEDULED")
        .first()
    )
    if active_block and not task.is_open:
        raise ConflictError("Task has scheduled time blocks; cancel them first.")
    db.delete(task)
    db.commit()


def complete_task(db: Session, user_id: int, task_id: int, actual_duration: int | None) -> Task:
    task = get_task(db, user_id, task_id)
    if task.status == TaskStatus.COMPLETED.value:
        raise ConflictError("Task is already completed.", code="TASK_ALREADY_COMPLETED")
    task.status = TaskStatus.COMPLETED.value
    task.completed_at = utcnow()
    if actual_duration is not None:
        task.actual_duration = actual_duration
    elif task.estimated_duration is not None:
        # Optimistic default: assume the estimate was met unless told otherwise.
        task.actual_duration = task.estimated_duration
    db.commit()
    db.refresh(task)
    return task


def counts_by_status(db: Session, user_id: int) -> dict[str, int]:
    rows = (
        db.query(Task.status, safunc.count(Task.id))
        .filter(Task.user_id == user_id)
        .group_by(Task.status)
        .all()
    )
    return {status: count for status, count in rows}
