"""Planner Agent: Strategic Schedule, Chronos Time Blocking & Task Engine."""

from __future__ import annotations

from app.agent.agents.base_agent import BaseSubAgent
from app.agent.tools.goals import CreateGoalTool, GetGoalsTool, UpdateGoalTool
from app.agent.tools.schedule import (
    CreateRecurringScheduleTool,
    CreateTimeBlockTool,
    DeleteTimeBlockTool,
    GetRecurringSchedulesTool,
    GetScheduleTool,
    UpdateRecurringScheduleTool,
    UpdateTimeBlockTool,
)
from app.agent.tools.tasks import (
    CompleteTasksTool,
    CompleteTaskTool,
    CreateTaskTool,
    DeleteTasksTool,
    DeleteTaskTool,
    GetTasksTool,
    GetTaskTool,
    GetTodayTasksTool,
    UpdateTaskTool,
)
from app.core.config import settings

PLANNER_SYSTEM_PROMPT = """You are Planner, the strategic time planning, Chronos scheduling, and task management engine for IRIS.
Your mission is to maximize the user's focus, maintain realistic time estimates, and ensure high-priority goals are achieved.

CAPABILITIES:
1. Schedule & Time Blocking (Chronos):
   - Inspect the daily calendar schedule using `get_schedule`.
   - Allocate focused time blocks for deep work or routines using `create_time_block`.
   - Adjust block start/end times or move them using `update_time_block`.
   - Remove blocks using `delete_time_block`.
   - Manage recurring weekly routines using `get_recurring_schedules`, `create_recurring_schedule`, and `update_recurring_schedule`.
2. Task Lifecycle:
   - Query pending or completed tasks using `get_tasks` and `get_task`.
   - Add new action items with priorities, deadlines, and time estimates using `create_task`.
   - Update deadlines, estimated durations, or priorities using `update_task`.
   - Mark single or bulk tasks as completed using `complete_task` and `complete_tasks`.
   - Delete obsolete tasks using `delete_task` and `delete_tasks`.
3. Goals & Strategic Alignment:
   - Review user milestones and quarterly goals using `get_goals`.
   - Create or update goals using `create_goal` and `update_goal`.

OPERATING RULES:
- Ground every schedule change in real time slots; avoid overlapping commitments.
- When organizing a day, query existing commitments first with `get_schedule` and `get_tasks`.
- Always confirm specific task titles, scheduled time ranges, and duration when reporting back.
"""


class PlannerAgent(BaseSubAgent):
    """Specialized worker for schedule optimization, calendar time blocks, and task management."""

    def __init__(self, model_spec: str | None = None) -> None:
        spec = model_spec or settings.ai_planner_model
        tools = [
            GetTodayTasksTool(),
            GetTasksTool(),
            GetTaskTool(),
            CreateTaskTool(),
            UpdateTaskTool(),
            CompleteTaskTool(),
            DeleteTaskTool(),
            CompleteTasksTool(),
            DeleteTasksTool(),
            GetScheduleTool(),
            CreateTimeBlockTool(),
            UpdateTimeBlockTool(),
            DeleteTimeBlockTool(),
            GetRecurringSchedulesTool(),
            CreateRecurringScheduleTool(),
            UpdateRecurringScheduleTool(),
            GetGoalsTool(),
            CreateGoalTool(),
            UpdateGoalTool(),
        ]
        super().__init__(
            name="Planner",
            role="Strategic Schedule, Task & Chronos Engine",
            system_prompt=PLANNER_SYSTEM_PROMPT,
            tools=tools,
            model_spec=spec,
        )


_planner_instance: PlannerAgent | None = None


def get_planner_agent(model_spec: str | None = None) -> PlannerAgent:
    """Return singleton or configured instance of PlannerAgent."""
    global _planner_instance
    if model_spec is not None:
        return PlannerAgent(model_spec=model_spec)
    if _planner_instance is None:
        _planner_instance = PlannerAgent()
    return _planner_instance
