"""Desktop CLI and Execution Agent Tools for IRIS.

Tools:
- execute_desktop_command: Run PowerShell/CLI commands with policy enforcement, timeout, background jobs, and postcondition verification.
- get_background_job_status: Inspect output and status of long-running background jobs.
- cancel_background_job: Stop or cancel running background tasks.
- inspect_desktop_process: Inspect running processes or check port listeners.
- find_latest_laptop_file: Locate the most recently modified file in a directory.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.execution.contracts import ExecutionRequest, ExecutionStatus
from app.execution.registry import desktop_executor
from app.execution.windows.shell import job_manager
from app.models.user import User


class ExecuteDesktopCommandParams(BaseModel):
    command: str = Field(
        ...,
        description="PowerShell or CLI command to execute on the Windows laptop (e.g. 'git status', 'pytest tests/', 'npm test', 'dir', 'python -m py_compile app.py').",
    )
    working_dir: str | None = Field(
        default=None,
        description="Working directory on the laptop to run in (e.g. 'C:\\kirtan\\IRIS', 'Desktop', 'Downloads', 'backend', or null for default repo).",
    )
    timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Timeout limit in seconds (default: 30s).",
    )
    background: bool = Field(
        default=False,
        description="Set to true for long-running processes (like dev servers, file watchers, or test suites) so they do not block the chat.",
    )
    verify_type: str | None = Field(
        default=None,
        description="Optional postcondition check: 'exit_code_zero', 'file_exists', 'file_contains', 'port_listening', 'output_contains'.",
    )
    verify_target: str | None = Field(
        default=None,
        description="Target path, port number, or regex pattern for the postcondition check.",
    )
    approval_token: str | None = Field(
        default=None,
        description="Approval token if authorizing a previously requested sensitive command.",
    )


class ExecuteDesktopCommandTool(Tool):
    name = "execute_desktop_command"
    description = (
        "Execute a PowerShell or shell CLI command on the Windows laptop with policy checks, timeouts, "
        "background execution support, and postcondition verification. Use for running scripts, git commands, "
        "tests, builds, or system utilities."
    )
    parameters_schema = ExecuteDesktopCommandParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        cmd = kwargs["command"]
        cwd = kwargs.get("working_dir")
        timeout = kwargs.get("timeout_seconds", 30.0)
        background = kwargs.get("background", False)
        verify_type = kwargs.get("verify_type")
        verify_target = kwargs.get("verify_target")
        approval_token = kwargs.get("approval_token")

        verify_spec = None
        if verify_type:
            verify_spec = {"type": verify_type}
            if verify_type in ("file_exists", "file_contains"):
                verify_spec["path"] = verify_target
            elif verify_type == "port_listening":
                verify_spec["port"] = int(verify_target) if verify_target and verify_target.isdigit() else 8000
            elif verify_type == "output_contains":
                verify_spec["pattern"] = verify_target

        req = ExecutionRequest(
            capability="shell_command",
            command=cmd,
            working_dir=cwd,
            timeout_seconds=timeout,
            background=background,
            verify_postcondition=verify_spec,
            approval_token=approval_token,
        )

        res = desktop_executor.execute(req)

        if res.status == ExecutionStatus.APPROVAL_REQUIRED:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="APPROVAL_REQUIRED",
                summary=res.approval_prompt or "Command requires user approval.",
                data={
                    "status": "APPROVAL_REQUIRED",
                    "approval_token": res.approval_token,
                    "command": cmd,
                    "permission_class": res.permission_class.value,
                },
            )

        if res.status == ExecutionStatus.DENIED:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=res.error_type or "PERMISSION_DENIED",
                summary=f"Command execution denied by security policy:\n{res.stderr}",
                data={"status": "DENIED", "stderr": res.stderr},
            )

        if background:
            summary = f"🚀 Started background job `{res.job_id}` for command: `{cmd}`. Use `get_background_job_status` to monitor."
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={"job_id": res.job_id, "command": cmd, "status": "RUNNING"},
                summary=summary,
            )

        output = (res.stdout or res.stderr or "Command finished with no output.").strip()
        v_str = f"\n[Postcondition Verified: {res.verification_details}]" if res.verified else ""
        summary = (
            f"Executed `{cmd}` (Exit {res.exit_code}, {res.duration_ms}ms){v_str}:\n```\n{output}\n```"
            if res.is_success
            else f"Command `{cmd}` failed (Exit {res.exit_code}):\n{res.stderr or res.stdout}"
        )

        return ToolResult(
            tool_name=self.name,
            success=res.is_success,
            data={
                "exit_code": res.exit_code,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "duration_ms": res.duration_ms,
                "verified": res.verified,
                "verification_details": res.verification_details,
                "permission_class": res.permission_class.value,
            },
            summary=summary,
        )


class GetBackgroundJobStatusParams(BaseModel):
    job_id: str | None = Field(
        default=None,
        description="Optional job identifier (e.g. 'job_a1b2c3d4'). If omitted, lists all tracked jobs.",
    )


class GetBackgroundJobStatusTool(Tool):
    name = "get_background_job_status"
    description = "Check the execution status, exit code, and recent output of long-running background tasks or servers."
    parameters_schema = GetBackgroundJobStatusParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        job_id = kwargs.get("job_id")
        if job_id:
            info = job_manager.get_job(job_id)
            if not info:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"No tracked job found with ID '{job_id}'.",
                    summary=f"Job `{job_id}` was not found.",
                )
            summary = (
                f"Job `{info.job_id}` Status: **{info.status}** (PID {info.pid or 'N/A'}, Exit {info.exit_code}):\n"
                f"Command: `{info.command}`\n"
                f"Output Preview:\n```\n{info.output_preview or 'No output yet.'}\n```"
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=info.model_dump(mode="json"),
                summary=summary,
            )

        jobs = job_manager.list_jobs()
        if not jobs:
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={"jobs": []},
                summary="No background jobs currently running or tracked.",
            )

        lines = [f"• `{j.job_id}` [{j.status}] PID {j.pid or 'N/A'}: `{j.command}`" for j in jobs]
        summary = f"Found {len(jobs)} background job(s):\n" + "\n".join(lines)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"jobs": [j.model_dump(mode="json") for j in jobs]},
            summary=summary,
        )


class CancelBackgroundJobParams(BaseModel):
    job_id: str = Field(..., description="ID of the running background job to terminate (e.g. 'job_a1b2c3d4').")


class CancelBackgroundJobTool(Tool):
    name = "cancel_background_job"
    description = "Terminate and cancel a running background command, development server, or test job."
    parameters_schema = CancelBackgroundJobParams
    read_only = False
    is_destructive = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        job_id = kwargs["job_id"].strip()
        ok = job_manager.cancel_job(job_id)
        if ok:
            summary = f"🛑 Cancelled background job `{job_id}` and terminated process tree."
            return ToolResult(tool_name=self.name, success=True, data={"job_id": job_id, "cancelled": True}, summary=summary)
        return ToolResult(tool_name=self.name, success=False, error=f"Could not cancel job '{job_id}' (not found or already ended).")


class InspectDesktopProcessParams(BaseModel):
    filter_name: str | None = Field(default=None, description="Optional process name or substring to search for (e.g. 'python', 'node', 'code').")
    port: int | None = Field(default=None, description="Optional TCP port number to check (e.g. 8000, 3000, 5173).")


class InspectDesktopProcessTool(Tool):
    name = "inspect_desktop_process"
    description = "Inspect running Windows processes or check which process is listening on a specific TCP port."
    parameters_schema = InspectDesktopProcessParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.execution.windows.processes import process_manager

        port = kwargs.get("port")
        filter_name = kwargs.get("filter_name")

        if port is not None:
            res = process_manager.inspect_port(int(port))
            status_txt = "LISTENING" if res.get("listening") else "CLOSED/NOT LISTENING"
            pids = res.get("pids", [])
            summary = f"Port {port} status: **{status_txt}** (PIDs: {pids or 'None'})."
            return ToolResult(tool_name=self.name, success=True, data=res, summary=summary)

        procs = process_manager.list_processes(filter_name=filter_name, limit=40)
        lines = [f"• PID {p['pid']}: **{p['name']}** ({p['memory_mb']} MB)" for p in procs]
        summary = f"Found {len(procs)} process(es)" + (f" matching '{filter_name}':\n" if filter_name else ":\n") + "\n".join(lines[:25])
        return ToolResult(tool_name=self.name, success=True, data={"processes": procs}, summary=summary)


class FindLatestLaptopFileParams(BaseModel):
    directory: str | None = Field(
        default=None,
        description="Directory or folder to search (e.g. 'Downloads', 'Desktop', 'C:\\kirtan\\IRIS', or null for repo).",
    )
    extension: str | None = Field(
        default=None,
        description="Optional file extension filter without dot (e.g. 'pdf', 'csv', 'py', 'json', 'log').",
    )


class FindLatestLaptopFileTool(Tool):
    name = "find_latest_laptop_file"
    description = "Find the most recently created or modified file in a directory (e.g. 'Find the latest PDF in Downloads')."
    parameters_schema = FindLatestLaptopFileParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        from app.execution.windows.filesystem import controlled_fs

        folder = kwargs.get("directory") or "Downloads"
        ext = kwargs.get("extension")
        res = controlled_fs.find_latest_file(directory=folder, extension=ext)

        if not res.get("success"):
            return ToolResult(tool_name=self.name, success=False, error=res.get("error", "No matching files found."))

        summary = (
            f"📄 Found latest file in `{folder}`: **{res.get('name')}**\n"
            f"Path: `{res.get('file_path')}`\n"
            f"Size: {round((res.get('size_bytes') or 0) / 1024, 1)} KB"
        )
        return ToolResult(tool_name=self.name, success=True, data=res, summary=summary)


def desktop_tools() -> list[Tool]:
    """Return the suite of desktop CLI and automation execution tools."""
    return [
        ExecuteDesktopCommandTool(),
        GetBackgroundJobStatusTool(),
        CancelBackgroundJobTool(),
        InspectDesktopProcessTool(),
        FindLatestLaptopFileTool(),
    ]
