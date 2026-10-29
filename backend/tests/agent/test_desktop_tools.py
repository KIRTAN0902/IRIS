"""Tests for desktop agent tools and Supervisor execution integration."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.agent.agents.operator import get_operator_agent
from app.agent.supervisor import IrisSupervisor
from app.agent.tools.desktop import (
    CancelBackgroundJobTool,
    ExecuteDesktopCommandTool,
    FindLatestLaptopFileTool,
    GetBackgroundJobStatusTool,
    InspectDesktopProcessTool,
    desktop_tools,
)
from app.core.security import get_current_user
from app.execution.policy import default_policy
from app.models.user import User


@pytest.fixture
def test_user(db: Session):
    return get_current_user(db)


# --- 1. OperatorAgent Tool Suite ---------------------------------------------

def test_operator_agent_has_desktop_tools():
    op = get_operator_agent()
    tool_names = list(op.registry._tools.keys())
    assert "execute_desktop_command" in tool_names
    assert "get_background_job_status" in tool_names
    assert "cancel_background_job" in tool_names
    assert "inspect_desktop_process" in tool_names
    assert "find_latest_laptop_file" in tool_names


# --- 2. Tool Execution Tests -------------------------------------------------

@pytest.mark.asyncio
async def test_execute_desktop_command_tool(db: Session, test_user: User):
    tool = ExecuteDesktopCommandTool()
    res = await tool.execute(
        db=db,
        user=test_user,
        command="Write-Output 'Hello Tool Execution'",
    )
    assert res.success is True
    assert "Hello Tool Execution" in res.data["stdout"]
    assert res.data["exit_code"] == 0


@pytest.mark.asyncio
async def test_execute_desktop_command_tool_approval_required(db: Session, test_user: User):
    tool = ExecuteDesktopCommandTool()
    res = await tool.execute(
        db=db,
        user=test_user,
        command="pip install scipy",
    )
    assert res.success is False
    assert res.error == "APPROVAL_REQUIRED"
    assert "approval_token" in res.data
    assert res.data["approval_token"].startswith("appr_")


@pytest.mark.asyncio
async def test_inspect_desktop_process_tool(db: Session, test_user: User):
    tool = InspectDesktopProcessTool()
    res = await tool.execute(db=db, user=test_user)
    assert res.success is True
    assert len(res.data["processes"]) > 0


@pytest.mark.asyncio
async def test_find_latest_laptop_file_tool(db: Session, test_user: User, tmp_path):
    f = tmp_path / "latest_doc.txt"
    f.write_text("sample document", encoding="utf-8")

    tool = FindLatestLaptopFileTool()
    res = await tool.execute(
        db=db,
        user=test_user,
        directory=str(tmp_path),
        extension="txt",
    )
    assert res.success is True
    assert res.data["name"] == "latest_doc.txt"


# --- 3. Supervisor Fast-Path Tests -------------------------------------------

def test_supervisor_fast_path_approval(db: Session, test_user: User):
    sup = IrisSupervisor()
    cmd = "Write-Output 'Authorized Fast Path'"
    token, _ = default_policy.issue_approval_token(cmd, r"C:\kirtan\IRIS", default_policy.classify_command(cmd)[0])

    resp, actions = sup.try_fast_path(db, test_user, {}, f"approve {token}")
    assert resp is not None
    assert "Authorized Execution Completed" in resp.message
    assert "Authorized Fast Path" in resp.message
    assert len(actions) == 1
    assert actions[0]["tool_name"] == "approve_command"


def test_supervisor_fast_path_open_vscode_repo(db: Session, test_user: User):
    sup = IrisSupervisor()
    resp, actions = sup.try_fast_path(db, test_user, {}, "open vs code in my iris repo")
    assert resp is not None
    assert "Opened" in resp.message or "VS Code" in resp.message or "Visual Studio Code" in resp.message
    assert len(actions) == 1


def test_supervisor_fast_path_open_downloads(db: Session, test_user: User):
    sup = IrisSupervisor()
    resp, actions = sup.try_fast_path(db, test_user, {}, "open my downloads folder")
    assert resp is not None
    assert "Downloads" in resp.message or "Opened" in resp.message
    assert len(actions) == 1
