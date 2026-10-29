"""Structured contracts and schemas for desktop command execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PermissionClass(str, Enum):
    """Execution risk categories for Windows automation."""

    CLASS_A_READ_ONLY = "CLASS_A_READ_ONLY"
    CLASS_B_ROUTINE = "CLASS_B_ROUTINE"
    CLASS_C_SENSITIVE = "CLASS_C_SENSITIVE"
    CLASS_D_DESTRUCTIVE = "CLASS_D_DESTRUCTIVE"


class ExecutionStatus(str, Enum):
    """Outcome of command execution."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    DENIED = "DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class ExecutionRequest(BaseModel):
    """Specification of an execution request to the desktop layer."""

    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    capability: str = Field(
        default="shell_command",
        description="Capability to execute, e.g. 'shell_command', 'read_file', 'write_file', 'list_files', 'search_files', 'launch_app', 'inspect_process'",
    )
    command: str | list[str] = Field(
        ...,
        description="The shell command string or structured argument array to execute.",
    )
    working_dir: str | None = Field(
        default=None,
        description="Explicit working directory. Defaults to workspace root.",
    )
    timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Maximum execution time before timeout.",
    )
    permission_class: PermissionClass | None = Field(
        default=None,
        description="Explicit or inferred permission class.",
    )
    approval_token: str | None = Field(
        default=None,
        description="Single-use approval token if pre-authorized by user.",
    )
    background: bool = Field(
        default=False,
        description="Whether to run asynchronously as a detached background job (e.g. dev servers, builds).",
    )
    environment_policy: dict[str, str] | None = Field(
        default=None,
        description="Optional environment variables to inject or override.",
    )
    output_format: str = Field(
        default="text",
        description="'text' or 'json'.",
    )
    verify_postcondition: dict[str, Any] | None = Field(
        default=None,
        description="Optional specification to verify after execution (file_exists, port_listening, process_running, etc.).",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary caller metadata for telemetry and correlation.",
    )


class ExecutionResult(BaseModel):
    """Comprehensive result of an execution attempt."""

    request_id: str
    status: ExecutionStatus
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    error_type: str | None = None
    verified: bool = False
    verification_details: str = ""
    permission_class: PermissionClass = PermissionClass.CLASS_A_READ_ONLY
    approval_required: bool = False
    approval_token: str | None = None
    approval_prompt: str | None = None
    job_id: str | None = None
    artifacts: list[str] = Field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS


class JobInfo(BaseModel):
    """Status metadata for long-running background tasks."""

    job_id: str
    command: str
    pid: int | None = None
    status: str = "RUNNING"  # RUNNING, COMPLETED, FAILED, CANCELLED
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    exit_code: int | None = None
    working_dir: str = ""
    output_preview: str = ""
