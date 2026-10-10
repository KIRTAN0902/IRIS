"""Tests for IRIS agent autonomous coding tools."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.agent.registry import default_registry
from app.agent.tools.coding import (
    GetCodingTaskStatusTool,
    ListCodingTasksTool,
    StartAutonomousCodingTool,
)
from app.core.security import get_current_user
from app.services import autonomous_coder_service as acs


def test_coding_tools_registered():
    assert default_registry.get("start_autonomous_coding") is not None
    assert default_registry.get("get_coding_task_status") is not None
    assert default_registry.get("list_coding_tasks") is not None
    assert default_registry.is_mutating("start_autonomous_coding")
    assert not default_registry.is_mutating("get_coding_task_status")


@pytest.mark.asyncio
async def test_coding_tools_execution(db: Session, user_id: int):
    user = get_current_user(db)

    # 1. Start coding task
    start_tool = StartAutonomousCodingTool()
    res = await start_tool.execute(
        db,
        user,
        instruction="Refactor helper functions and run pytest",
        workspace="iris",
    )
    assert res.success
    task_id = res.data["task_id"]
    assert task_id is not None
    assert "Launched autonomous coding task" in res.summary

    # 2. Get status
    status_tool = GetCodingTaskStatusTool()
    status_res = await status_tool.execute(db, user, task_id=task_id)
    assert status_res.success
    assert status_res.data["task_id"] == task_id

    # 3. List tasks
    list_tool = ListCodingTasksTool()
    list_res = await list_tool.execute(db, user)
    assert list_res.success
    assert any(t["task_id"] == task_id for t in list_res.data)
