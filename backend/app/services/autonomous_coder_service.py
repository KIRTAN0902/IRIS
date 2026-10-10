"""Autonomous Coding Service using Google Antigravity SDK.

Allows IRIS to run background autonomous coding tasks (writing code, running tests,
and editing repositories) triggered remotely from your phone or web dashboard.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Any
import uuid

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Known workspace shortcuts
WORKSPACE_MAP: dict[str, str] = {
    "iris": r"C:\kirtan\IRIS",
    "outreach": r"C:\kirtan\Engines\Outreach Agent",
    "outreach agent": r"C:\kirtan\Engines\Outreach Agent",
}


def resolve_workspace(name_or_path: str | None) -> str:
    """Resolves a workspace name or path, falling back to C:\\kirtan\\IRIS."""
    if not name_or_path:
        return r"C:\kirtan\IRIS"

    low = name_or_path.strip().lower()
    if low in WORKSPACE_MAP:
        return WORKSPACE_MAP[low]

    p = Path(name_or_path).resolve()
    if p.exists() and p.is_dir():
        return str(p)

    return r"C:\kirtan\IRIS"


class CodingTask(BaseModel):
    task_id: str
    instruction: str
    workspace: str
    status: str = "QUEUED"  # QUEUED, RUNNING, COMPLETED, FAILED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    output: str = ""
    error: str | None = None
    logs: list[str] = Field(default_factory=list)


# In-memory storage for active and recent background coding tasks
_TASKS: dict[str, CodingTask] = {}


async def _execute_antigravity_agent(task: CodingTask) -> None:
    task.status = "RUNNING"
    task.logs.append(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] Started autonomous agent in workspace: {task.workspace}")

    try:
        from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig

        api_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")

        system_prompt = (
            "You are an expert autonomous software engineer working in this workspace. "
            "Inspect files, edit or write code, execute commands/tests to verify correctness, "
            "and fix any issues. When done, provide a clear, concise summary of the files modified "
            "and test results."
        )

        config = LocalAgentConfig(
            system_instructions=system_prompt,
            workspaces=[task.workspace],
            api_key=api_key,
            capabilities=CapabilitiesConfig(),
        )

        task.logs.append(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] Initialized Antigravity Agent runtime.")

        async with Agent(config) as agent:
            response = await agent.chat(task.instruction)

            tokens: list[str] = []
            async for token in response:
                tokens.append(token)

            task.output = "".join(tokens)

        task.status = "COMPLETED"
        task.completed_at = datetime.now(UTC)
        task.logs.append(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] Autonomous coding task completed successfully.")

    except Exception as exc:
        task.status = "FAILED"
        task.error = str(exc)
        task.completed_at = datetime.now(UTC)
        task.logs.append(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] Task failed: {exc}")
        logger.exception("Autonomous coding task failed: %s", exc)


def launch_coding_task(instruction: str, workspace: str | None = None) -> CodingTask:
    """Spawns an autonomous Antigravity coding task in the background."""
    resolved_ws = resolve_workspace(workspace)
    task_id = str(uuid.uuid4())[:8]

    task = CodingTask(
        task_id=task_id,
        instruction=instruction,
        workspace=resolved_ws,
        status="QUEUED",
    )
    _TASKS[task_id] = task

    # Run agent in background safely regardless of whether called from async loop or worker thread
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_execute_antigravity_agent(task))
    except RuntimeError:
        import threading
        t = threading.Thread(
            target=lambda: asyncio.run(_execute_antigravity_agent(task)),
            daemon=True,
        )
        t.start()

    return task


def get_coding_task(task_id: str) -> CodingTask | None:
    return _TASKS.get(task_id)


def list_coding_tasks(limit: int = 20) -> list[CodingTask]:
    return sorted(_TASKS.values(), key=lambda t: t.created_at, reverse=True)[:limit]
