"""Antigravity terminal tools for the Operator agent.

These drive the persistent ``agy`` ConPTY session instead of launching a new
window, so chat follow-ups preserve the agent's working memory.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field
from pathlib import Path
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.user import User
from app.services.agy_bridge import AgyError, agy_manager


def _project_for_target(db: Session, user: User, target: str | None, *, write: bool = False):
    from app.models.coding_project import CodingProject

    rows=db.query(CodingProject).filter_by(user_id=user.id,active=True).all()
    needle=(target or "").strip().casefold()
    if needle:
        try:
            path=Path(target).expanduser()
            matches=[p for p in rows if path.is_absolute() and Path(p.directory).resolve()==path.resolve()]
        except (OSError,RuntimeError):
            matches=[]
        if not matches:
            matches=[p for p in rows if needle in [p.name.casefold(),*(a.casefold() for a in (p.aliases or []))]]
    else:
        matches=[p for p in rows if p.is_active]
    if len(matches)!=1:raise AgyError("Select one registered coding project before using Antigravity")
    project=matches[0]
    if not project.read_access or (write and (not project.write_access or not project.command_access)):
        raise AgyError("The selected project does not grant the required Antigravity permissions")
    return project


def _authorized_session(db: Session, user: User, session_key: str | None, *, write: bool = False):
    session=agy_manager.find_session(session_key or agy_manager.current_session_key)
    if session is None:raise AgyError("No active Antigravity session")
    _project_for_target(db,user,session.directory,write=write)
    return session


class AgyAttachParams(BaseModel):
    directory: str = Field(
        ...,
        description="Project alias or absolute path (e.g. 'iris', 'marketory', 'C:/kirtan/Nexus').",
    )
    alias: str | None = Field(None, description="Optional short session alias.")


class AgyPromptParams(BaseModel):
    instruction: str = Field(..., description="Coding instruction for the Antigravity agent.")
    session_key: str | None = Field(
        None, description="Attached session alias; defaults to the current session."
    )


class AgySlashParams(BaseModel):
    command: str = Field(..., description="Native agy slash command, e.g. '/usage'.")
    session_key: str | None = Field(None, description="Attached session alias.")


class AgyStatusParams(BaseModel):
    session_key: str | None = Field(None, description="Attached session alias.")


class AgyAttachDirectoryTool(Tool):
    name = "agy_attach_directory"
    description = (
        "Attach IRIS to a persistent Antigravity CLI session in an existing project "
        "directory. Reuses the session when already running."
    )
    parameters_schema = AgyAttachParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        try:
            project=_project_for_target(db,user,kwargs["directory"],write=True)
            session = await asyncio.to_thread(
                agy_manager.spawn_or_attach,
                project.directory,
                kwargs.get("alias") or project.name,
                governed=True,
            )
        except AgyError as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(exc),
                summary=f"Could not attach Antigravity: {exc}",
            )
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=session.to_dict(),
            summary=f"Antigravity attached in '{session.alias}' ({session.directory}).",
        )


class AgyExecutePromptTool(Tool):
    name = "agy_execute_prompt"
    description = (
        "Legacy operation. Do not send coding prompts directly; create a reviewable coding task "
        "through Coding Projects and wait for the user's approval."
    )
    parameters_schema = AgyPromptParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            success=False,
            error="A reviewed coding brief must be approved before IRIS sends a coding task to Antigravity.",
            summary="Prompt not sent. Prepare and approve the task in Coding Projects.",
        )


class AgyRunSlashCommandTool(Tool):
    name = "agy_run_slash_command"
    description = (
        "Run a native Antigravity slash command such as /resume, /models, /usage, "
        "/clear, /compact, /status, or /help in the active session."
    )
    parameters_schema = AgySlashParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        key = kwargs.get("session_key") or agy_manager.current_session_key
        command = kwargs["command"].strip()
        if not command.startswith("/"):
            command = f"/{command}"
        try:
            _authorized_session(db,user,key,write=True)
            result = await asyncio.to_thread(agy_manager.send_raw_input, key, command)
        except AgyError as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(exc),
                summary=f"Could not run {command}: {exc}",
            )
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=result,
            summary=f"Ran {command} in Antigravity session '{key}'.",
        )


class AgySessionStatusTool(Tool):
    name = "agy_get_session_status_and_diff"
    description = (
        "Read the live Antigravity session state, recent terminal output, and the last "
        "harvested git diff summary for a project."
    )
    parameters_schema = AgyStatusParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        try:
            session=_authorized_session(db,user,kwargs.get("session_key"),write=False)
        except AgyError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="No active authorized Antigravity session.",
                summary="No active authorized Antigravity session.",
            )
        data = {
            **session.to_dict(),
            "last_diff": session.last_diff[:8000],
            "recent_output": session.recent(120),
        }
        summary = (
            f"Antigravity '{session.alias}' is {session.state}. "
            f"{session.last_summary or 'No completed task yet.'}"
        )
        return ToolResult(tool_name=self.name, success=True, data=data, summary=summary)


def agy_tools() -> list[Tool]:
    return [
        AgyAttachDirectoryTool(),
        AgyExecutePromptTool(),
        AgyRunSlashCommandTool(),
        AgySessionStatusTool(),
    ]
