"""API routes for persistent Remote Workspaces and GitHub sync."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.coding.remote_companion_client import RemoteCompanionClient, RemoteCompanionError
from app.core.database import get_db
from app.models.coding_project import CodingProject
from app.models.remote_workspace import RemoteWorkspace
from app.models.user import User

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str = "Primary Cloud Workspace"
    repo_url: str
    branch: str = "main"
    project_id: int | None = None
    github_pat: str | None = None
    companion_url: str | None = None


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    companion_url: str | None = None
    branch: str | None = None
    task_branch: str | None = None


class CommitApprovalRequest(BaseModel):
    message: str
    author_name: str = "IRIS Coding Co-worker"
    author_email: str = "coworker@iris.dev"


class PushApprovalRequest(BaseModel):
    branch: str
    github_pat: str


def _get_client(ws: RemoteWorkspace) -> RemoteCompanionClient:
    return RemoteCompanionClient(base_url=ws.companion_url)


@router.get("")
def list_workspaces(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """List all remote workspaces owned by current user."""
    workspaces = db.query(RemoteWorkspace).filter_by(user_id=user.id).order_by(RemoteWorkspace.updated_at.desc()).all()
    return workspaces


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    req: CreateWorkspaceRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Create a persistent remote workspace, optionally provisioning it on the remote companion."""
    ws_id = str(uuid4())
    ws = RemoteWorkspace(
        id=ws_id,
        user_id=user.id,
        project_id=req.project_id,
        name=req.name.strip(),
        repo_url=req.repo_url.strip(),
        branch=req.branch.strip(),
        companion_url=req.companion_url or os.getenv("REMOTE_COMPANION_URL"),
        status="idle",
        last_active_at=datetime.now(UTC),
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)

    # If companion is configured, provision in background or synchronous call
    client = _get_client(ws)
    try:
        res = await client.provision_workspace(
            workspace_id=ws.id,
            repo_url=ws.repo_url,
            branch=ws.branch,
            github_pat=req.github_pat,
        )
        ws.base_commit_sha = res.get("base_commit_sha")
        ws.current_commit_sha = res.get("base_commit_sha")
        ws.status = "idle"
        db.commit()
        db.refresh(ws)
    except Exception:
        # Keep workspace recorded as idle/offline even if companion is sleeping
        pass

    return ws


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Get status, active task branch, and git diff for a remote workspace."""
    ws = db.query(RemoteWorkspace).filter_by(id=workspace_id, user_id=user.id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    diff_data = None
    client = _get_client(ws)
    try:
        diff_data = await client.get_diff(workspace_id)
    except Exception:
        pass

    return {
        "workspace": ws,
        "diff": diff_data,
    }


@router.patch("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    req: UpdateWorkspaceRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Update workspace attributes, such as updating companion_url or branch."""
    ws = db.query(RemoteWorkspace).filter_by(id=workspace_id, user_id=user.id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if req.name is not None:
        ws.name = req.name.strip()
    if req.companion_url is not None:
        ws.companion_url = req.companion_url.strip()
    if req.branch is not None:
        ws.branch = req.branch.strip()
    if req.task_branch is not None:
        ws.task_branch = req.task_branch.strip()
    ws.last_active_at = datetime.now(UTC)
    db.commit()
    db.refresh(ws)
    return ws


@router.post("/{workspace_id}/checkpoint")
async def checkpoint_workspace(
    workspace_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Durable checkpoint: captures in-flight uncommitted diff and saves patch to PostgreSQL."""
    ws = db.query(RemoteWorkspace).filter_by(id=workspace_id, user_id=user.id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    client = _get_client(ws)
    try:
        res = await client.checkpoint(workspace_id)
        ws.previous_patch = ws.uncommitted_patch
        ws.uncommitted_patch = res.get("patch")
        ws.checkpoint_hash = res.get("patch_hash")
        ws.checkpoint_version = (ws.checkpoint_version or 0) + 1
        ws.checkpoint_at = datetime.now(UTC)
        ws.current_commit_sha = res.get("current_commit_sha")
        ws.last_active_at = datetime.now(UTC)
        db.commit()
        db.refresh(ws)
        return {
            "checkpointed": True,
            "workspace_id": workspace_id,
            "has_uncommitted": bool(ws.uncommitted_patch),
            "checkpoint_version": ws.checkpoint_version,
            "checkpoint_hash": ws.checkpoint_hash,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Checkpoint failed: {e}")


@router.post("/{workspace_id}/recover")
async def recover_workspace(
    workspace_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Recover workspace after compute sleep/restart using git branch and saved uncommitted patch."""
    ws = db.query(RemoteWorkspace).filter_by(id=workspace_id, user_id=user.id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    ws.status = "recovering"
    db.commit()

    client = _get_client(ws)
    target_branch = ws.task_branch or ws.branch
    try:
        await client.provision_workspace(workspace_id, ws.repo_url, target_branch)
        if ws.uncommitted_patch:
            await client.restore(
                workspace_id=workspace_id,
                branch=target_branch,
                patch=ws.uncommitted_patch,
                expected_hash=ws.checkpoint_hash,
            )
        ws.status = "idle"
        ws.last_active_at = datetime.now(UTC)
        db.commit()
        db.refresh(ws)
        return {
            "recovered": True,
            "workspace_id": workspace_id,
            "branch": target_branch,
            "version": ws.checkpoint_version,
        }
    except Exception as e:
        ws.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Recovery failed: {e}")


@router.post("/{workspace_id}/commit")
async def commit_workspace_changes(
    workspace_id: str,
    req: CommitApprovalRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Commit changes to task branch following explicit user approval."""
    ws = db.query(RemoteWorkspace).filter_by(id=workspace_id, user_id=user.id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    client = _get_client(ws)
    try:
        res = await client.commit(
            workspace_id=workspace_id,
            message=req.message,
            author_name=req.author_name,
            author_email=req.author_email,
        )
        ws.current_commit_sha = res.get("commit_sha")
        ws.uncommitted_patch = None  # committed, patch clear!
        db.commit()
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workspace_id}/push")
async def push_workspace_changes(
    workspace_id: str,
    req: PushApprovalRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Push committed task branch to GitHub remote following explicit user approval."""
    ws = db.query(RemoteWorkspace).filter_by(id=workspace_id, user_id=user.id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    client = _get_client(ws)
    try:
        res = await client.push(
            workspace_id=workspace_id,
            branch=req.branch,
            github_pat=req.github_pat,
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workspace_id}/stop")
async def stop_workspace_execution(
    workspace_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Stop active engine execution in remote workspace."""
    ws = db.query(RemoteWorkspace).filter_by(id=workspace_id, user_id=user.id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    client = _get_client(ws)
    res = await client.stop(workspace_id)
    ws.status = "stopped"
    db.commit()
    return res
