"""Tool Registry for discovering, documenting, and safely executing agent tools."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.awareness import (
    GetCompletedTasksTool,
    GetConversationTool,
    GetPersonalProfileTool,
    GetSituationTool,
    SearchConversationsTool,
)
from app.agent.tools.actions import action_tools
from app.agent.tools.base import Tool
from app.agent.tools.finance import finance_tools
from app.agent.tools.goals import CreateGoalTool, GetGoalsTool, UpdateGoalTool
from app.agent.tools.intelligence import (
    GetAttentionItemsTool,
    GetCurrentRecommendationTool,
    GetCurrentStateTool,
    GetDecisionHistoryTool,
    GetDecisionRecommendationTool,
    GetTodayStateTool,
    RecordDecisionFeedbackTool,
)
from app.agent.tools.memory import (
    ForgetMemoryTool,
    ListMemoriesTool,
    SaveMemoryTool,
    SearchMemoryTool,
)
from app.agent.tools.schedule import (
    CreateRecurringScheduleTool,
    CreateTimeBlockTool,
    DeleteTimeBlockTool,
    GetRecurringSchedulesTool,
    GetScheduleTool,
    UpdateRecurringScheduleTool,
    UpdateTimeBlockTool,
)
from app.agent.tools.startup import GetOutreachStatusTool, GetStartupStatusTool, LogOutreachTool
from app.agent.tools.tasks import (
    CompleteTasksTool,
    CompleteTaskTool,
    CreateTaskTool,
    DeleteTasksTool,
    DeleteTaskTool,
    GetTasksTool,
    GetTaskTool,
    UpdateTaskTool,
)
from app.ai.provider import ToolDefinition
from app.models.user import User


class ToolRegistry:
    """Registry maintaining available tools for the IRIS Agent."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_specs(self) -> list[dict[str, Any]]:
        return [tool.to_spec() for tool in self._tools.values()]

    def list_tool_definitions(self) -> list[ToolDefinition]:
        return [tool.to_tool_definition() for tool in self._tools.values()]

    def is_mutating(self, name: str) -> bool:
        tool = self.get(name)
        return bool(tool and tool.mutates_state)

    async def execute(
        self,
        name: str,
        db: Session,
        user: User,
        parameters: dict[str, Any] | None = None,
    ) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(
                tool_name=name,
                success=False,
                error=f"Tool '{name}' is not registered in the system.",
                summary=f"Attempted to call unrecognized tool '{name}'.",
            )
        return await tool.execute(db, user, **(parameters or {}))


def create_default_registry() -> ToolRegistry:
    """Create and populate registry with all default IRIS tools."""
    registry = ToolRegistry()

    # Awareness (situation + personal model)
    registry.register(GetSituationTool())
    registry.register(GetPersonalProfileTool())
    registry.register(GetCompletedTasksTool())
    registry.register(SearchConversationsTool())
    registry.register(GetConversationTool())

    # Tasks
    registry.register(GetTasksTool())
    registry.register(GetTaskTool())
    registry.register(CreateTaskTool())
    registry.register(UpdateTaskTool())
    registry.register(CompleteTaskTool())
    registry.register(DeleteTaskTool())
    registry.register(CompleteTasksTool())
    registry.register(DeleteTasksTool())

    # Goals
    registry.register(GetGoalsTool())
    registry.register(CreateGoalTool())
    registry.register(UpdateGoalTool())

    # Schedule
    registry.register(GetScheduleTool())
    registry.register(CreateTimeBlockTool())
    registry.register(UpdateTimeBlockTool())
    registry.register(DeleteTimeBlockTool())
    registry.register(GetRecurringSchedulesTool())
    registry.register(CreateRecurringScheduleTool())
    registry.register(UpdateRecurringScheduleTool())

    # Startup
    registry.register(GetStartupStatusTool())
    registry.register(GetOutreachStatusTool())
    registry.register(LogOutreachTool())

    # Intelligence
    registry.register(GetTodayStateTool())
    registry.register(GetCurrentStateTool())
    registry.register(GetAttentionItemsTool())
    registry.register(GetDecisionRecommendationTool())
    registry.register(GetCurrentRecommendationTool())
    registry.register(GetDecisionHistoryTool())
    registry.register(RecordDecisionFeedbackTool())

    # Memory
    registry.register(SaveMemoryTool())
    registry.register(SearchMemoryTool())
    registry.register(ForgetMemoryTool())
    registry.register(ListMemoriesTool())

    # Everything else the app can change (projects, CRM, focus, profile, ...)
    for tool in action_tools():
        registry.register(tool)

    # Money: transactions, budgets, bills, savings goals
    for tool in finance_tools():
        registry.register(tool)

    return registry



# Global default instance
default_registry = create_default_registry()

