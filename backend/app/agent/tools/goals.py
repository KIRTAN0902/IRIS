"""Goal management tools for the IRIS Agent."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.enums import GoalStatus, LifeArea
from app.models.user import User
from app.schemas.goal import GoalCreate, GoalUpdate
from app.services import goal_service

# --- 1. GetGoalsTool ---


class GetGoalsParams(BaseModel):
    area: LifeArea | None = Field(None, description="Filter goals by life area")
    status: GoalStatus | None = Field(
        None, description="Filter by status (ACTIVE, ACHIEVED, BEHIND, PAUSED)"
    )


class GetGoalsTool(Tool):
    name = "get_goals"
    description = "Retrieve the user's goals hierarchy or list by area/status."
    parameters_schema = GetGoalsParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        goals = goal_service.list_goals(
            db, user.id, area=kwargs.get("area"), status=kwargs.get("status")
        )
        goals_data = [
            {
                "id": g.id,
                "name": g.name,
                "area": g.area,
                "status": g.status,
                "parent_goal_id": g.parent_goal_id,
                "target_value": g.target_value,
                "current_value": g.current_value,
                "unit": g.unit,
                "deadline": g.deadline.isoformat() if g.deadline else None,
                "progress_fraction": g.progress_fraction,
            }
            for g in goals
        ]
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"goals": goals_data, "total": len(goals_data)},
            summary=f"Retrieved {len(goals_data)} goals.",
        )


# --- 2. CreateGoalTool ---


class CreateGoalParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Clear, measurable goal name")
    area: LifeArea = Field(
        LifeArea.STARTUP, description="Life area (STARTUP, COLLEGE, INTERNSHIP, PERSONAL)"
    )
    parent_goal_id: int | None = Field(None, description="Optional parent goal ID for hierarchy")
    target_value: float | None = Field(None, description="Target numerical outcome (e.g. 5, 100)")
    current_value: float = Field(0.0, description="Current starting value")
    unit: str | None = Field(
        None, description="Measurement unit (e.g. 'customers', 'leads', 'GPA')"
    )
    deadline: datetime | None = Field(None, description="Target deadline")
    description: str | None = Field(None, description="Context or strategy notes")


class CreateGoalTool(Tool):
    name = "create_goal"
    description = "Create a new goal or sub-goal in IRIS."
    parameters_schema = CreateGoalParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        goal_in = GoalCreate(**kwargs)
        goal = goal_service.create_goal(db, user.id, goal_in)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"goal_id": goal.id, "name": goal.name, "area": goal.area},
            summary=f"Created goal #{goal.id}: '{goal.name}' ({goal.area}).",
            audit_event={"action": "CREATE_GOAL", "goal_id": goal.id, "name": goal.name},
        )


# --- 3. UpdateGoalTool ---


class UpdateGoalParams(BaseModel):
    goal_id: int = Field(..., description="ID of the goal to update")
    name: str | None = Field(None, min_length=1, max_length=255)
    current_value: float | None = None
    target_value: float | None = None
    unit: str | None = None
    status: GoalStatus | None = None
    deadline: datetime | None = None
    description: str | None = None


class UpdateGoalTool(Tool):
    name = "update_goal"
    description = "Update goal progress, status, target value, or deadline."
    parameters_schema = UpdateGoalParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        goal_id = kwargs.pop("goal_id")
        goal_update = GoalUpdate(**kwargs)
        goal = goal_service.update_goal(db, user.id, goal_id, goal_update)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "goal_id": goal.id,
                "name": goal.name,
                "current_value": goal.current_value,
                "status": goal.status,
            },
            summary=f"Updated goal #{goal.id} ('{goal.name}').",
            audit_event={"action": "UPDATE_GOAL", "goal_id": goal.id, "updates": kwargs},
        )
