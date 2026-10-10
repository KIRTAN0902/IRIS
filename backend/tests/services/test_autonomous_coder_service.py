"""Tests for autonomous coding service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services import autonomous_coder_service as acs


def test_resolve_workspace():
    assert acs.resolve_workspace("iris") == r"C:\kirtan\IRIS"
    assert acs.resolve_workspace("outreach") == r"C:\kirtan\Engines\Outreach Agent"
    assert acs.resolve_workspace(None) == r"C:\kirtan\IRIS"


@pytest.mark.asyncio
async def test_launch_and_get_coding_task():
    # Mock Antigravity Agent execution to avoid making external LLM calls during unit tests
    mock_response = AsyncMock()

    async def mock_tokens():
        yield "Tests passed."
        yield " Code committed."

    mock_response.__aiter__ = lambda self: mock_tokens()

    mock_agent = AsyncMock()
    mock_agent.chat.return_value = mock_response
    mock_agent.__aenter__.return_value = mock_agent

    with patch("google.antigravity.Agent", return_value=mock_agent):
        task = acs.launch_coding_task(
            instruction="Write a hello world test",
            workspace="iris",
        )
        assert task.task_id is not None
        assert task.workspace == r"C:\kirtan\IRIS"

        # Check retrieval
        retrieved = acs.get_coding_task(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id

        # List tasks
        all_tasks = acs.list_coding_tasks()
        assert any(t.task_id == task.task_id for t in all_tasks)
