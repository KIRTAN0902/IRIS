"""IRIS Agent Tools package."""

from app.agent.tools.base import Tool
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
    CompleteTaskTool,
    CreateTaskTool,
    DeleteTaskTool,
    GetTasksTool,
    GetTaskTool,
    UpdateTaskTool,
)

__all__ = [
    "Tool",
    # Tasks
    "GetTasksTool",
    "GetTaskTool",
    "CreateTaskTool",
    "UpdateTaskTool",
    "CompleteTaskTool",
    "DeleteTaskTool",
    # Goals
    "GetGoalsTool",
    "CreateGoalTool",
    "UpdateGoalTool",
    # Schedule
    "GetScheduleTool",
    "CreateTimeBlockTool",
    "UpdateTimeBlockTool",
    "DeleteTimeBlockTool",
    "GetRecurringSchedulesTool",
    "CreateRecurringScheduleTool",
    "UpdateRecurringScheduleTool",
    # Startup
    "GetStartupStatusTool",
    "GetOutreachStatusTool",
    "LogOutreachTool",
    # Intelligence
    "GetTodayStateTool",
    "GetCurrentStateTool",
    "GetAttentionItemsTool",
    "GetDecisionRecommendationTool",
    "GetCurrentRecommendationTool",
    "GetDecisionHistoryTool",
    "RecordDecisionFeedbackTool",
]

