"""Autonomous Coding Tools for the IRIS Agent using Google Antigravity.

Enables IRIS to accept high-level programming instructions from your phone or chat,
spawn an autonomous Antigravity coding agent in the background, and track execution.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.user import User
from app.services import autonomous_coder_service as acs


class StartCodingParams(BaseModel):
    instruction: str = Field(
        ...,
        description="The programming task to execute (e.g. 'Add a test for outreach endpoint', 'Refactor auth error handling', 'Build a new model')",
    )
    workspace: str | None = Field(
        None,
        description="Target workspace ('iris', 'outreach', or absolute path). Defaults to 'iris'.",
    )


class GetCodingTaskParams(BaseModel):
    task_id: str = Field(..., description="The task ID returned when the coding task was launched.")


class StartAutonomousCodingTool(Tool):
    name = "start_autonomous_coding"
    description = (
        "Launch an autonomous Antigravity coding agent in the background to inspect files, edit code, "
        "and execute terminal tests in a project repository. Returns a task ID immediately."
    )
    parameters_schema = StartCodingParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        instruction = kwargs["instruction"]
        workspace = kwargs.get("workspace")
        task = acs.launch_coding_task(instruction=instruction, workspace=workspace)

        summary = (
            f"Launched autonomous coding task #{task.task_id} in '{task.workspace}'. "
            f"Antigravity is now running in the background. Check status using get_coding_task_status."
        )
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=task.model_dump(mode="json"),
            summary=summary,
        )


class GetCodingTaskStatusTool(Tool):
    name = "get_coding_task_status"
    description = "Check the live status, logs, and output of an autonomous coding task."
    parameters_schema = GetCodingTaskParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        task_id = kwargs["task_id"]
        task = acs.get_coding_task(task_id)
        if not task:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"No coding task found with ID '{task_id}'.",
                summary=f"Task #{task_id} not found.",
            )

        summary = f"Coding task #{task.task_id} is {task.status}. Workspace: {task.workspace}"
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=task.model_dump(mode="json"),
            summary=summary,
        )


class ListCodingTasksTool(Tool):
    name = "list_coding_tasks"
    description = "List recent autonomous coding tasks and their completion status."
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        tasks = acs.list_coding_tasks(limit=10)
        data = [t.model_dump(mode="json") for t in tasks]
        summary = f"Found {len(tasks)} recent coding task(s)."
        return ToolResult(tool_name=self.name, success=True, data=data, summary=summary)


def coding_tools() -> list[Tool]:
    """Factory returning all autonomous coding agent tools."""
    return [
        StartAutonomousCodingTool(),
        GetCodingTaskStatusTool(),
        ListCodingTasksTool(),
    ]
