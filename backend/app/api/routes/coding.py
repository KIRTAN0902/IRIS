"""FastAPI routes for autonomous background coding tasks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.models.user import User
from app.services import autonomous_coder_service as acs

router = APIRouter(prefix="/coding", tags=["coding"])


class LaunchCodingTaskRequest(BaseModel):
    instruction: str = Field(..., min_length=3, description="Programming instructions for Antigravity")
    workspace: str | None = Field(None, description="Workspace ('iris', 'outreach', or absolute path)")


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
async def launch_task(
    req: LaunchCodingTaskRequest,
    user: User = Depends(current_user),
):
    """Deprecated unsafe entry point; use the reviewed coding execution workflow."""
    raise HTTPException(
        status_code=410,
        detail={"code":"APPROVAL_REQUIRED","message":"Direct coding task launch is disabled. Register a workspace and create/approve a brief at /api/coding/execution/tasks."},
    )


@router.get("/tasks")
def list_tasks(
    limit: int = 20,
    user: User = Depends(current_user),
):
    """List recent autonomous coding tasks."""
    tasks = acs.list_coding_tasks(limit=limit)
    return [t.model_dump(mode="json") for t in tasks]


@router.get("/tasks/{task_id}")
def get_task(
    task_id: str,
    user: User = Depends(current_user),
):
    """Get status, live logs, and output of a specific coding task."""
    task = acs.get_coding_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task #{task_id} not found.")
    return task.model_dump(mode="json")
