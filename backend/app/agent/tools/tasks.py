"""Task management tools for the IRIS Agent."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.utils.datetime import from_local, localize_date_boundaries, to_local, utcnow
from app.agent.schemas import ToolResult
from app.agent.tools.base import RiskLevel, Tool, VerificationStrategy
from app.models.enums import EnergyLevel, LifeArea, TaskPriority, TaskStatus
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate
from app.services import task_service

# --- 0. GetTodayTasksTool ---


class GetTodayTasksParams(BaseModel):
    area: LifeArea | None = Field(
        None, description="Optional filter by area (COLLEGE, INTERNSHIP, STARTUP, PERSONAL)"
    )
    include_completed: bool = Field(
        True, description="Whether to include tasks completed today"
    )


class GetTodayTasksTool(Tool):
    name = "get_today_tasks"
    description = (
        "Retrieve all tasks relevant to today: tasks due today, overdue tasks, in-progress tasks, "
        "and tasks completed today, formatted with priority rankings and estimated durations."
    )
    parameters_schema = GetTodayTasksParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        tz_str = user.timezone or "UTC"
        now_local = to_local(utcnow(), tz_str)
        today_start_utc, today_end_utc = localize_date_boundaries(now_local.date(), tz_str)

        area_filter = kwargs.get("area")
        include_completed = kwargs.get("include_completed", True)

        q_open = (
            db.query(Task)
            .filter(
                Task.user_id == user.id,
                Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]),
            )
        )
        if area_filter:
            area_str = area_filter.value if hasattr(area_filter, "value") else str(area_filter)
            q_open = q_open.filter(Task.area == area_str)

        open_tasks = q_open.order_by(Task.deadline.asc().nullslast(), Task.priority.desc()).all()

        overdue: list[dict[str, Any]] = []
        due_today: list[dict[str, Any]] = []
        other_open: list[dict[str, Any]] = []
        in_progress: list[dict[str, Any]] = []

        for t in open_tasks:
            t_data = {
                "id": t.id,
                "title": t.title,
                "area": t.area,
                "priority": t.priority,
                "status": t.status,
                "deadline": to_local(t.deadline, tz_str).strftime("%H:%M") if t.deadline else None,
                "deadline_full": t.deadline.isoformat() if t.deadline else None,
                "estimated_duration": t.estimated_duration,
                "description": t.description,
            }
            if t.status == TaskStatus.IN_PROGRESS.value:
                in_progress.append(t_data)

            if t.deadline:
                if t.deadline < today_start_utc:
                    overdue.append(t_data)
                elif t.deadline <= today_end_utc:
                    due_today.append(t_data)
                else:
                    other_open.append(t_data)
            else:
                other_open.append(t_data)

        completed_today: list[dict[str, Any]] = []
        if include_completed:
            q_comp = (
                db.query(Task)
                .filter(
                    Task.user_id == user.id,
                    Task.status == TaskStatus.COMPLETED.value,
                    Task.completed_at >= today_start_utc,
                    Task.completed_at <= today_end_utc,
                )
            )
            if area_filter:
                area_str = area_filter.value if hasattr(area_filter, "value") else str(area_filter)
                q_comp = q_comp.filter(Task.area == area_str)
            completed_tasks = q_comp.order_by(Task.completed_at.desc()).all()
            for t in completed_tasks:
                completed_today.append({
                    "id": t.id,
                    "title": t.title,
                    "area": t.area,
                    "priority": t.priority,
                    "completed_at": to_local(t.completed_at, tz_str).strftime("%H:%M") if t.completed_at else None,
                    "actual_duration": t.actual_duration,
                })

        today_str = now_local.strftime("%A, %d %B %Y")
        summary_parts = []
        if due_today:
            summary_parts.append(f"{len(due_today)} due today")
        if in_progress:
            summary_parts.append(f"{len(in_progress)} in progress")
        if overdue:
            summary_parts.append(f"{len(overdue)} overdue")
        if other_open:
            summary_parts.append(f"{len(other_open)} open")
        if completed_today:
            summary_parts.append(f"{len(completed_today)} completed today")

        summary_text = (
            f"Tasks for {today_str}: " + ", ".join(summary_parts)
            if summary_parts
            else f"No tasks scheduled or due for today ({today_str})."
        )

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "today_date": today_str,
                "due_today": due_today,
                "in_progress": in_progress,
                "overdue": overdue,
                "other_open": other_open,
                "completed_today": completed_today,
                "counts": {
                    "due_today": len(due_today),
                    "in_progress": len(in_progress),
                    "overdue": len(overdue),
                    "other_open": len(other_open),
                    "completed_today": len(completed_today),
                    "total_active": len(open_tasks),
                },
            },
            summary=summary_text,
        )


# --- 1. GetTasksTool ---


class GetTasksParams(BaseModel):
    area: LifeArea | None = Field(
        None, description="Filter by area (COLLEGE, INTERNSHIP, STARTUP, PERSONAL)"
    )
    status: TaskStatus | None = Field(
        None, description="Filter by status (TODO, IN_PROGRESS, COMPLETED, etc.)"
    )
    open_only: bool = Field(True, description="If True, only returns open tasks (TODO/IN_PROGRESS)")
    overdue_only: bool = Field(
        False, description="If True, only returns tasks that have passed their deadline"
    )
    limit: int = Field(20, ge=1, le=100, description="Max number of tasks to return")


class GetTasksTool(Tool):
    name = "get_tasks"
    description = (
        "Retrieve the user's tasks with optional filters for area, status, open_only, and overdue."
    )
    parameters_schema = GetTasksParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        tasks, total = task_service.list_tasks(
            db,
            user.id,
            area=kwargs.get("area"),
            status=kwargs.get("status"),
            open_only=kwargs.get("open_only", True),
            overdue_only=kwargs.get("overdue_only", False),
            limit=kwargs.get("limit", 20),
        )
        task_data = [
            {
                "id": t.id,
                "title": t.title,
                "area": t.area,
                "priority": t.priority,
                "status": t.status,
                "deadline": t.deadline.isoformat() if t.deadline else None,
                "estimated_duration": t.estimated_duration,
                "is_overdue": t.is_overdue,
            }
            for t in tasks
        ]
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"tasks": task_data, "total": total},
            summary=f"Found {len(task_data)} tasks (out of {total} total).",
        )


# --- 2. GetTaskTool ---


class GetTaskParams(BaseModel):
    task_id: int = Field(..., description="ID of the specific task to retrieve")


class GetTaskTool(Tool):
    name = "get_task"
    description = "Retrieve full details of a specific task by its ID."
    parameters_schema = GetTaskParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        task_id = kwargs["task_id"]
        try:
            t = task_service.get_task(db, user.id, task_id)
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "area": t.area,
                    "priority": t.priority,
                    "status": t.status,
                    "deadline": t.deadline.isoformat() if t.deadline else None,
                    "estimated_duration": t.estimated_duration,
                    "actual_duration": t.actual_duration,
                    "goal_id": t.goal_id,
                    "project_id": t.project_id,
                    "is_overdue": t.is_overdue,
                },
                summary=f"Retrieved task #{t.id}: '{t.title}'.",
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                summary=f"Could not find task #{task_id}.",
            )


# --- 3. CreateTaskTool ---


class CreateTaskParams(BaseModel):
    title: str = Field(
        ..., min_length=1, max_length=255, description="Clear, actionable task title"
    )
    area: LifeArea = Field(
        LifeArea.PERSONAL, description="Life area (COLLEGE, INTERNSHIP, STARTUP, PERSONAL)"
    )
    priority: TaskPriority = Field(
        TaskPriority.MEDIUM, description="Priority (CRITICAL, HIGH, MEDIUM, LOW)"
    )
    deadline: datetime | None = Field(
        None, description="ISO datetime for deadline, e.g. '2026-09-02T18:00:00'"
    )
    due_today: bool | None = Field(
        None, description="If True, automatically sets deadline to today at 23:59 in the user's timezone"
    )
    estimated_duration: int | None = Field(
        None, ge=5, le=720, description="Estimated minutes (e.g. 45, 90)"
    )
    description: str | None = Field(None, description="Detailed description or notes")
    energy_level: EnergyLevel | None = Field(
        None, description="Energy requirement (DEEP_WORK, NORMAL, LOW_ENERGY)"
    )
    goal_id: int | None = Field(None, description="Optional parent goal ID")
    project_id: int | None = Field(None, description="Optional parent project ID")


class CreateTaskTool(Tool):
    name = "create_task"
    description = "Create a new task in IRIS with specified title, area, deadline, and priority."
    parameters_schema = CreateTaskParams
    risk_level = RiskLevel.ORDINARY_WRITE
    verification_strategy = VerificationStrategy.DB_CHECK
    category = "tasks"

    async def verify(self, db: Session, user: User, result: ToolResult, **kwargs: Any) -> bool:
        task_id = result.data.get("task_id") if isinstance(result.data, dict) else None
        if not task_id:
            return False
        task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
        return task is not None

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        if kwargs.get("due_today") and not kwargs.get("deadline"):
            tz_str = user.timezone or "UTC"
            now_local = to_local(utcnow(), tz_str)
            kwargs["deadline"] = from_local(now_local.date(), tz_str, end_of_day=True)
        kwargs.pop("due_today", None)

        task_in = TaskCreate(**kwargs)
        task = task_service.create_task(db, user.id, task_in)
        summary = f"Created task #{task.id}: '{task.title}' ({task.area})"
        if task.deadline:
            summary += f" due {to_local(task.deadline, user.timezone).strftime('%a %d %b %H:%M')}"
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "task_id": task.id,
                "title": task.title,
                "area": task.area,
                "deadline": task.deadline.isoformat() if task.deadline else None,
            },
            summary=summary,
            audit_event={"action": "CREATE_TASK", "task_id": task.id, "title": task.title},
        )


# --- 4. UpdateTaskTool ---


class UpdateTaskParams(BaseModel):
    task_id: int = Field(..., description="ID of the task to update")
    title: str | None = Field(None, min_length=1, max_length=255)
    area: LifeArea | None = None
    priority: TaskPriority | None = None
    status: TaskStatus | None = None
    deadline: datetime | None = None
    estimated_duration: int | None = None
    description: str | None = None
    goal_id: int | None = None
    project_id: int | None = None


class UpdateTaskTool(Tool):
    name = "update_task"
    description = (
        "Update an existing task's fields such as title, deadline, area, priority, or status."
    )
    parameters_schema = UpdateTaskParams
    risk_level = RiskLevel.ORDINARY_WRITE
    verification_strategy = VerificationStrategy.DB_CHECK
    category = "tasks"

    async def verify(self, db: Session, user: User, result: ToolResult, **kwargs: Any) -> bool:
        task_id = result.data.get("task_id") if isinstance(result.data, dict) else None
        if not task_id:
            return False
        task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
        return task is not None

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        task_id = kwargs.pop("task_id")
        task_update = TaskUpdate(**kwargs)
        task = task_service.update_task(db, user.id, task_id, task_update)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"task_id": task.id, "title": task.title, "status": task.status},
            summary=f"Updated task #{task.id} ('{task.title}').",
            audit_event={"action": "UPDATE_TASK", "task_id": task.id, "updates": kwargs},
        )


# --- 5. CompleteTaskTool ---


class CompleteTaskParams(BaseModel):
    task_id: int = Field(..., description="ID of the task to mark as completed")
    actual_duration: int | None = Field(
        None, ge=1, le=1440, description="Actual minutes spent (optional)"
    )


class CompleteTaskTool(Tool):
    name = "complete_task"
    description = "Mark an open task as completed, optionally recording actual duration spent."
    parameters_schema = CompleteTaskParams
    risk_level = RiskLevel.ORDINARY_WRITE
    verification_strategy = VerificationStrategy.DB_CHECK
    category = "tasks"

    async def verify(self, db: Session, user: User, result: ToolResult, **kwargs: Any) -> bool:
        task_id = kwargs.get("task_id") or (result.data.get("task_id") if isinstance(result.data, dict) else None)
        if not task_id:
            return False
        task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
        return task is not None and task.status == TaskStatus.COMPLETED.value

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        task_id = kwargs["task_id"]
        actual_duration = kwargs.get("actual_duration")
        task = task_service.complete_task(db, user.id, task_id, actual_duration)
        summary = f"Marked task #{task.id} ('{task.title}') as completed"
        if task.actual_duration:
            summary += f" ({task.actual_duration}m spent)"
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "task_id": task.id,
                "title": task.title,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            },
            summary=summary,
            audit_event={
                "action": "COMPLETE_TASK",
                "task_id": task.id,
                "actual_duration": task.actual_duration,
            },
        )


# --- 6. DeleteTaskTool ---


class DeleteTaskParams(BaseModel):
    task_id: int = Field(..., description="ID of the task to delete")


class DeleteTaskTool(Tool):
    name = "delete_task"
    description = "Permanently delete a task. Only use when explicitly instructed by the user."
    parameters_schema = DeleteTaskParams
    is_destructive = True
    risk_level = RiskLevel.REVERSIBLE
    verification_strategy = VerificationStrategy.DB_CHECK
    category = "tasks"

    async def verify(self, db: Session, user: User, result: ToolResult, **kwargs: Any) -> bool:
        task_id = kwargs.get("task_id") or (result.data.get("deleted_task_id") if isinstance(result.data, dict) else None)
        if not task_id:
            return False
        task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
        return task is None

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        task_id = kwargs["task_id"]
        task = task_service.get_task(db, user.id, task_id)
        title = task.title
        task_service.delete_task(db, user.id, task_id)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"deleted_task_id": task_id},
            summary=f"Deleted task #{task_id} ('{title}').",
            audit_event={"action": "DELETE_TASK", "task_id": task_id, "title": title},
        )


# --- 7. Bulk tools: one call for many tasks ---


class BulkTaskIdsParams(BaseModel):
    task_ids: list[int] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="IDs of every task to act on (look them up with get_tasks first)",
    )


def _bulk_apply(task_ids: list[int], action) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    done: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for task_id in dict.fromkeys(task_ids):  # de-duplicate, keep order
        try:
            done.append(action(task_id))
        except Exception as exc:  # noqa: BLE001 - report per task, keep going
            failed.append({"task_id": task_id, "error": str(exc) or type(exc).__name__})
    return done, failed


def _bulk_result(name: str, verb: str, done: list[dict], failed: list[dict]) -> ToolResult:
    summary = f"{verb} {len(done)} task{'s' if len(done) != 1 else ''}"
    if done:
        summary += ": " + ", ".join(f"#{d['task_id']} {d['title']}" for d in done[:8])
        if len(done) > 8:
            summary += f" and {len(done) - 8} more"
    if failed:
        summary += f" ({len(failed)} could not be {verb.lower()})"
    return ToolResult(
        tool_name=name,
        success=bool(done),
        data={"done": done, "failed": failed},
        error="; ".join(f"#{f['task_id']}: {f['error']}" for f in failed) or None,
        summary=summary + ".",
    )


class DeleteTasksTool(Tool):
    name = "delete_tasks"
    description = (
        "Permanently delete several tasks in ONE call. Use this instead of repeated "
        "delete_task calls whenever more than one task should go. Only when the user asked."
    )
    parameters_schema = BulkTaskIdsParams
    is_destructive = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        def delete(task_id: int) -> dict[str, Any]:
            title = task_service.get_task(db, user.id, task_id).title
            task_service.delete_task(db, user.id, task_id)
            return {"task_id": task_id, "title": title}

        done, failed = _bulk_apply(kwargs["task_ids"], delete)
        return _bulk_result(self.name, "Deleted", done, failed)


class CompleteTasksTool(Tool):
    name = "complete_tasks"
    description = (
        "Mark several tasks as completed in ONE call. Use this instead of repeated "
        "complete_task calls whenever more than one task is done."
    )
    parameters_schema = BulkTaskIdsParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        def complete(task_id: int) -> dict[str, Any]:
            task = task_service.complete_task(db, user.id, task_id, None)
            return {"task_id": task.id, "title": task.title}

        done, failed = _bulk_apply(kwargs["task_ids"], complete)
        return _bulk_result(self.name, "Completed", done, failed)


def task_tools() -> list[Tool]:
    """Return all standard task management tools."""
    return [
        GetTodayTasksTool(),
        GetTasksTool(),
        GetTaskTool(),
        CreateTaskTool(),
        UpdateTaskTool(),
        CompleteTaskTool(),
        DeleteTaskTool(),
        CompleteTasksTool(),
        DeleteTasksTool(),
    ]
