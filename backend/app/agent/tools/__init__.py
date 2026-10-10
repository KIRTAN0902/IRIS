"""IRIS Agent Tools package."""

from app.agent.tools.awareness import (
    GetCompletedTasksTool,
    GetConversationTool,
    GetPersonalProfileTool,
    GetSituationTool,
    SearchConversationsTool,
)
from app.agent.tools.base import Tool
from app.agent.tools.coding import (
    GetCodingTaskStatusTool,
    ListCodingTasksTool,
    StartAutonomousCodingTool,
    coding_tools,
)
from app.agent.tools.email import (
    CreateEmailDraftTool,
    GetEmailAccountsTool,
    GetEmailDetailsTool,
    ListUnreadEmailsTool,
    SearchEmailsTool,
    SendEmailTool,
    email_tools,
)
from app.agent.tools.mesh import (
    GetDeviceMeshStatusTool,
    LockWorkstationTool,
    RingMyPhoneTool,
    SyncClipboardTool,
    mesh_tools,
)
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

__all__ = [
    "Tool",
    # Awareness
    "GetSituationTool",
    "GetPersonalProfileTool",
    "GetCompletedTasksTool",
    "SearchConversationsTool",
    "GetConversationTool",
    # Tasks
    "GetTasksTool",
    "GetTaskTool",
    "CreateTaskTool",
    "UpdateTaskTool",
    "CompleteTaskTool",
    "DeleteTaskTool",
    "CompleteTasksTool",
    "DeleteTasksTool",
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
    # Memory
    "SaveMemoryTool",
    "SearchMemoryTool",
    "ForgetMemoryTool",
    "ListMemoriesTool",
    # Email
    "email_tools",
    "GetEmailAccountsTool",
    "ListUnreadEmailsTool",
    "SearchEmailsTool",
    "GetEmailDetailsTool",
    "CreateEmailDraftTool",
    "SendEmailTool",
    # Coding
    "coding_tools",
    "StartAutonomousCodingTool",
    "GetCodingTaskStatusTool",
    "ListCodingTasksTool",
    # Mesh
    "mesh_tools",
    "RingMyPhoneTool",
    "LockWorkstationTool",
    "SyncClipboardTool",
    "GetDeviceMeshStatusTool",
]


