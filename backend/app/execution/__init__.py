"""Desktop Execution Package for IRIS.

Provides controlled, policy-enforced, and verifiable execution of Windows
shell commands, filesystem operations, application launching, and background jobs.
"""

from app.execution.contracts import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    JobInfo,
    PermissionClass,
)
from app.execution.policy import ExecutionPolicy, default_policy, redact_secrets
from app.execution.registry import DesktopExecutionRegistry, desktop_executor
from app.execution.verification import verify_postcondition
from app.execution.windows.apps import WindowsAppLauncher, app_launcher
from app.execution.windows.filesystem import ControlledFileSystem, controlled_fs
from app.execution.windows.processes import WindowsProcessManager, process_manager
from app.execution.windows.shell import (
    BackgroundJobManager,
    WindowsShellExecutor,
    job_manager,
    windows_shell,
)

__all__ = [
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionStatus",
    "JobInfo",
    "PermissionClass",
    "ExecutionPolicy",
    "default_policy",
    "redact_secrets",
    "DesktopExecutionRegistry",
    "desktop_executor",
    "verify_postcondition",
    "WindowsShellExecutor",
    "windows_shell",
    "BackgroundJobManager",
    "job_manager",
    "ControlledFileSystem",
    "controlled_fs",
    "WindowsAppLauncher",
    "app_launcher",
    "WindowsProcessManager",
    "process_manager",
]
