"""Schedule management tools for the IRIS Agent."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.utils.datetime import to_local
from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.enums import TimeBlockStatus, TimeBlockType
from app.models.recurring_schedule import RecurringSchedule
from app.models.user import User
from app.schemas.time_block import TimeBlockCreate, TimeBlockUpdate
from app.services import schedule_service, time_engine

# --- 1. GetScheduleTool ---


class GetScheduleParams(BaseModel):
    start: datetime | None = Field(
        None, description="Start ISO datetime of window (defaults to now)"
    )
    end: datetime | None = Field(
        None, description="End ISO datetime of window (defaults to end of day)"
    )


class GetScheduleTool(Tool):
    name = "get_schedule"
    description = (
        "Retrieve scheduled time blocks, calendar events, and free availability intervals."
    )
    parameters_schema = GetScheduleParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        start = kwargs.get("start")
        end = kwargs.get("end")
        blocks = schedule_service.list_time_blocks(db, user.id, start=start, end=end)
        avail = time_engine.compute_availability(db, user.id, window_start=start, window_end=end)

        blocks_data = [
            {
                "id": b.id,
                "task_id": b.task_id,
                "start_time": b.start_time.isoformat(),
                "end_time": b.end_time.isoformat(),
                "type": b.type,
                "status": b.status,
                "notes": b.notes,
                "duration_minutes": b.duration_minutes,
            }
            for b in blocks
        ]
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "time_blocks": blocks_data,
                "total_free_minutes": avail.total_free_minutes,
                "free_intervals": [
                    {
                        "start": iv.start.isoformat(),
                        "end": iv.end.isoformat(),
                        "minutes": iv.minutes,
                    }
                    for iv in avail.free_intervals
                ],
            },
            summary=(
                f"Found {len(blocks_data)} time blocks and "
                f"{avail.total_free_minutes}m of free availability."
            ),
        )


# --- 2. CreateTimeBlockTool ---


class CreateTimeBlockParams(BaseModel):
    start_time: datetime = Field(..., description="Start ISO datetime for the block")
    end_time: datetime = Field(..., description="End ISO datetime for the block")
    task_id: int | None = Field(None, description="Optional task ID to associate")
    type: TimeBlockType = Field(
        TimeBlockType.FOCUS, description="Type (FOCUS, BREAK, MEETING, PERSONAL)"
    )
    notes: str | None = Field(None, description="Reason or focus notes")
    allow_overlap: bool = Field(False, description="Whether to allow overlapping existing blocks")


class CreateTimeBlockTool(Tool):
    name = "create_time_block"
    description = (
        "Schedule a new time block on the user's timeline (e.g. 90m focus session or meeting)."
    )
    parameters_schema = CreateTimeBlockParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        block_in = TimeBlockCreate(**kwargs)
        block = schedule_service.create_time_block(db, user.id, block_in)
        st_str = to_local(block.start_time, user.timezone).strftime("%H:%M")
        et_str = to_local(block.end_time, user.timezone).strftime("%H:%M")
        summary = f"Scheduled {block.duration_minutes}m {block.type} block ({st_str}–{et_str})"
        if block.task_id:
            summary += f" for task #{block.task_id}"
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "block_id": block.id,
                "start_time": block.start_time.isoformat(),
                "end_time": block.end_time.isoformat(),
                "duration_minutes": block.duration_minutes,
            },
            summary=summary,
            audit_event={
                "action": "CREATE_TIME_BLOCK",
                "block_id": block.id,
                "duration": block.duration_minutes,
            },
        )


# --- 3. UpdateTimeBlockTool ---


class UpdateTimeBlockParams(BaseModel):
    block_id: int = Field(..., description="ID of the time block to update")
    start_time: datetime | None = None
    end_time: datetime | None = None
    status: TimeBlockStatus | None = None
    notes: str | None = None


class UpdateTimeBlockTool(Tool):
    name = "update_time_block"
    description = "Move, resize, or update status of an existing time block."
    parameters_schema = UpdateTimeBlockParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        block_id = kwargs.pop("block_id")
        block_update = TimeBlockUpdate(**kwargs)
        block = schedule_service.update_time_block(db, user.id, block_id, block_update)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "block_id": block.id,
                "start_time": block.start_time.isoformat(),
                "end_time": block.end_time.isoformat(),
                "status": block.status,
            },
            summary=f"Updated time block #{block.id}.",
            audit_event={"action": "UPDATE_TIME_BLOCK", "block_id": block.id, "updates": kwargs},
        )


# --- 4. DeleteTimeBlockTool ---


class DeleteTimeBlockParams(BaseModel):
    block_id: int = Field(..., description="ID of the time block to remove")


class DeleteTimeBlockTool(Tool):
    name = "delete_time_block"
    description = "Delete or cancel a scheduled time block."
    parameters_schema = DeleteTimeBlockParams
    is_destructive = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        block_id = kwargs["block_id"]
        schedule_service.delete_time_block(db, user.id, block_id)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"deleted_block_id": block_id},
            summary=f"Removed time block #{block_id}.",
            audit_event={"action": "DELETE_TIME_BLOCK", "block_id": block_id},
        )


# --- 5. GetRecurringSchedulesTool ---


class GetRecurringSchedulesTool(Tool):
    name = "get_recurring_schedules"
    description = "Retrieve the user's weekly recurring routines and hard constraints."
    parameters_schema = None

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        scheds = (
            db.query(RecurringSchedule)
            .filter(RecurringSchedule.user_id == user.id)
            .order_by(RecurringSchedule.start_time.asc())
            .all()
        )
        data = [
            {
                "id": s.id,
                "name": s.name,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "days_of_week": s.days_of_week,
                "is_hard_constraint": s.is_hard_constraint,
                "status": s.status,
            }
            for s in scheds
        ]
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"recurring_schedules": data},
            summary=f"Found {len(data)} recurring schedules.",
        )


# --- 6. CreateRecurringScheduleTool ---


class CreateRecurringScheduleParams(BaseModel):
    name: str = Field(..., description="Routine or commitment name (e.g. 'Yoga', 'Internship')")
    start_time: str = Field(..., description="Start time HH:MM, e.g. '06:00'")
    end_time: str = Field(..., description="End time HH:MM, e.g. '07:30'")
    days_of_week: str = Field(
        "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        description="Comma separated days (e.g. 'Mon,Tue,Wed,Thu,Fri')",
    )
    is_hard_constraint: bool = Field(True, description="Whether this block is a hard commitment")


class CreateRecurringScheduleTool(Tool):
    name = "create_recurring_schedule"
    description = "Create a weekly recurring routine or hard constraint."
    parameters_schema = CreateRecurringScheduleParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        sched = RecurringSchedule(
            user_id=user.id,
            name=kwargs["name"],
            start_time=kwargs["start_time"],
            end_time=kwargs["end_time"],
            days_of_week=kwargs.get("days_of_week", "Mon,Tue,Wed,Thu,Fri,Sat,Sun"),
            is_hard_constraint=kwargs.get("is_hard_constraint", True),
            status="ACTIVE",
            type="FIXED" if kwargs.get("is_hard_constraint", True) else "FLEXIBLE",
        )
        db.add(sched)
        db.commit()
        db.refresh(sched)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "id": sched.id,
                "name": sched.name,
                "start_time": sched.start_time,
                "end_time": sched.end_time,
            },
            summary=(
                f"Created recurring routine '{sched.name}' "
                f"({sched.start_time}–{sched.end_time})."
            ),
            audit_event={
                "action": "CREATE_RECURRING_SCHEDULE",
                "schedule_id": sched.id,
                "name": sched.name,
            },
        )


# --- 7. UpdateRecurringScheduleTool ---


class UpdateRecurringScheduleParams(BaseModel):
    schedule_id: int = Field(..., description="ID of the recurring schedule to update")
    name: str | None = Field(None, description="Updated name")
    start_time: str | None = Field(None, description="Start time HH:MM")
    end_time: str | None = Field(None, description="End time HH:MM")
    days_of_week: str | None = Field(None, description="Comma separated days")
    is_hard_constraint: bool | None = Field(None, description="Hard constraint flag")
    status: str | None = Field(None, description="ACTIVE or PAUSED")


class UpdateRecurringScheduleTool(Tool):
    name = "update_recurring_schedule"
    description = "Update an existing recurring routine or hard constraint."
    parameters_schema = UpdateRecurringScheduleParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        sched_id = kwargs.pop("schedule_id")
        sched = (
            db.query(RecurringSchedule)
            .filter(RecurringSchedule.id == sched_id, RecurringSchedule.user_id == user.id)
            .first()
        )
        if not sched:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Recurring schedule #{sched_id} not found.",
            )

        for k, v in kwargs.items():
            if v is not None:
                setattr(sched, k, v)
        if "is_hard_constraint" in kwargs and kwargs["is_hard_constraint"] is not None:
            sched.type = "FIXED" if kwargs["is_hard_constraint"] else "FLEXIBLE"

        db.commit()
        db.refresh(sched)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "id": sched.id,
                "name": sched.name,
                "start_time": sched.start_time,
                "end_time": sched.end_time,
                "status": sched.status,
            },
            summary=(
                f"Updated recurring schedule '{sched.name}' "
                f"({sched.start_time}–{sched.end_time})."
            ),
            audit_event={
                "action": "UPDATE_RECURRING_SCHEDULE",
                "schedule_id": sched.id,
                "updates": kwargs,
            },
        )

