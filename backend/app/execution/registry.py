"""Central Desktop Execution Registry: Policy gatekeeper, executor, and verifier."""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.execution.contracts import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    PermissionClass,
)
from app.execution.policy import default_policy, redact_secrets
from app.execution.verification import verify_postcondition
from app.execution.windows.apps import app_launcher
from app.execution.windows.filesystem import controlled_fs
from app.execution.windows.processes import process_manager
from app.execution.windows.shell import job_manager, windows_shell

logger = get_logger("iris.execution.registry")


class DesktopExecutionRegistry:
    """Coordinates Windows capabilities, policy verification, secret scrubbing, and output verification."""

    def __init__(self, policy=default_policy) -> None:
        self.policy = policy

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a desktop command or capability through the security boundary."""
        from app.core.config import settings
        if not getattr(settings, "desktop_cli_enabled", True):
            return ExecutionResult(
                request_id=request.request_id,
                status=ExecutionStatus.DENIED,
                error_type="FEATURE_DISABLED",
                stderr="Desktop CLI execution is disabled by configuration.",
                permission_class=PermissionClass.CLASS_A_READ_ONLY,
            )

        capability = request.capability
        cmd_raw = request.command
        cwd = request.working_dir or r"C:\kirtan\IRIS"

        # 1. Classify command permissions
        perm_class, reason = self.policy.classify_command(
            command=cmd_raw,
            cwd=cwd,
            capability=capability,
        )

        # 2. Check Class D (Destructive / Privileged)
        if perm_class == PermissionClass.CLASS_D_DESTRUCTIVE and self.policy.block_class_d:
            logger.warning("Class D command blocked by policy: %s (Reason: %s)", cmd_raw, reason)
            return ExecutionResult(
                request_id=request.request_id,
                status=ExecutionStatus.DENIED,
                error_type="PERMISSION_DENIED",
                stderr=f"Operation blocked by security policy: {reason}",
                permission_class=perm_class,
            )

        # 3. Check Class C / Sensitive Approval Requirement
        if perm_class in (PermissionClass.CLASS_C_SENSITIVE, PermissionClass.CLASS_D_DESTRUCTIVE):
            if self.policy.require_approval_for_class_c:
                if request.approval_token:
                    ok, appr_err = self.policy.verify_and_consume_token(
                        token=request.approval_token,
                        command=cmd_raw,
                        cwd=cwd,
                    )
                    if not ok:
                        return ExecutionResult(
                            request_id=request.request_id,
                            status=ExecutionStatus.DENIED,
                            error_type="APPROVAL_REJECTED",
                            stderr=f"Approval verification failed: {appr_err}",
                            permission_class=perm_class,
                        )
                else:
                    # Issue approval token and request authorization
                    token, prompt = self.policy.issue_approval_token(
                        command=cmd_raw,
                        cwd=cwd,
                        permission_class=perm_class,
                    )
                    return ExecutionResult(
                        request_id=request.request_id,
                        status=ExecutionStatus.APPROVAL_REQUIRED,
                        approval_required=True,
                        approval_token=token,
                        approval_prompt=prompt,
                        permission_class=perm_class,
                        stderr="Approval required before executing sensitive command.",
                    )

        # 4. Dispatch by capability
        result = self._dispatch(request, perm_class)

        # 5. Postcondition verification
        if result.status == ExecutionStatus.SUCCESS:
            v_ok, v_detail = verify_postcondition(request.verify_postcondition, result)
            result.verified = v_ok
            result.verification_details = v_detail
            if not v_ok and request.verify_postcondition:
                result.status = ExecutionStatus.FAILURE
                result.error_type = "POSTCONDITION_FAILED"

        # 6. Scrub secrets from output
        result.stdout = redact_secrets(result.stdout)
        result.stderr = redact_secrets(result.stderr)
        if result.approval_prompt:
            result.approval_prompt = redact_secrets(result.approval_prompt)

        return result

    def _dispatch(self, req: ExecutionRequest, perm_class: PermissionClass) -> ExecutionResult:
        cap = req.capability
        cmd = req.command
        cwd = req.working_dir

        # Capability: shell_command
        if cap == "shell_command":
            if req.background:
                cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
                job_info = job_manager.start_job(
                    command=cmd_str,
                    cwd=cwd,
                    env=req.environment_policy,
                )
                return ExecutionResult(
                    request_id=req.request_id,
                    status=ExecutionStatus.SUCCESS,
                    stdout=f"Started background job {job_info.job_id} (PID {job_info.pid}).",
                    job_id=job_info.job_id,
                    permission_class=perm_class,
                )

            # Synchronous
            exit_code, out, err, dur = windows_shell.execute_sync(
                command=cmd,
                cwd=cwd,
                timeout_seconds=req.timeout_seconds,
                env=req.environment_policy,
            )
            status = ExecutionStatus.SUCCESS if exit_code == 0 else ExecutionStatus.FAILURE
            if "timed out" in err.lower():
                status = ExecutionStatus.TIMEOUT
            return ExecutionResult(
                request_id=req.request_id,
                status=status,
                exit_code=exit_code,
                stdout=out,
                stderr=err,
                duration_ms=dur,
                permission_class=perm_class,
            )

        # Capability: read_file
        if cap == "read_file":
            fpath = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            res = controlled_fs.read_file(fpath)
            if res.get("success"):
                return ExecutionResult(
                    request_id=req.request_id,
                    status=ExecutionStatus.SUCCESS,
                    exit_code=0,
                    stdout=res.get("content", ""),
                    permission_class=perm_class,
                )
            return ExecutionResult(
                request_id=req.request_id,
                status=ExecutionStatus.FAILURE,
                exit_code=1,
                stderr=res.get("error", "Read file failed."),
                permission_class=perm_class,
            )

        # Capability: write_file
        if cap == "write_file":
            meta = req.metadata or {}
            fpath = str(meta.get("file_path") or cmd)
            content = str(meta.get("content") or "")
            mode = str(meta.get("mode") or "overwrite")
            res = controlled_fs.write_file(fpath, content, mode=mode)
            if res.get("success"):
                return ExecutionResult(
                    request_id=req.request_id,
                    status=ExecutionStatus.SUCCESS,
                    exit_code=0,
                    stdout=res.get("message", "File written successfully."),
                    permission_class=perm_class,
                )
            return ExecutionResult(
                request_id=req.request_id,
                status=ExecutionStatus.FAILURE,
                exit_code=1,
                stderr=res.get("error", "Write file failed."),
                permission_class=perm_class,
            )

        # Capability: list_files
        if cap == "list_files":
            dir_path = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            res = controlled_fs.list_directory(dir_path or cwd)
            if res.get("success"):
                entries = res.get("entries", [])
                formatted = "\n".join(
                    [f"📁 {e['name']}/" if e["type"] == "directory" else f"📄 {e['name']} ({e['size_bytes'] or 0}b)" for e in entries]
                )
                return ExecutionResult(
                    request_id=req.request_id,
                    status=ExecutionStatus.SUCCESS,
                    exit_code=0,
                    stdout=formatted,
                    permission_class=perm_class,
                )
            return ExecutionResult(
                request_id=req.request_id,
                status=ExecutionStatus.FAILURE,
                exit_code=1,
                stderr=res.get("error", "List files failed."),
                permission_class=perm_class,
            )

        # Capability: search_files
        if cap == "search_files":
            query = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            res = controlled_fs.search_files(query=query, directory=cwd)
            if res.get("success"):
                matches = res.get("matches", [])
                lines = [f"• `{m['name']}` ({m['path']})" for m in matches]
                return ExecutionResult(
                    request_id=req.request_id,
                    status=ExecutionStatus.SUCCESS,
                    exit_code=0,
                    stdout="\n".join(lines) if lines else "No matching files found.",
                    permission_class=perm_class,
                )
            return ExecutionResult(
                request_id=req.request_id,
                status=ExecutionStatus.FAILURE,
                exit_code=1,
                stderr=res.get("error", "Search files failed."),
                permission_class=perm_class,
            )

        # Capability: find_latest_file
        if cap == "find_latest_file":
            meta = req.metadata or {}
            ext = meta.get("extension")
            res = controlled_fs.find_latest_file(directory=cwd, extension=ext)
            if res.get("success"):
                return ExecutionResult(
                    request_id=req.request_id,
                    status=ExecutionStatus.SUCCESS,
                    exit_code=0,
                    stdout=json.dumps(res, indent=2),
                    permission_class=perm_class,
                )
            return ExecutionResult(
                request_id=req.request_id,
                status=ExecutionStatus.FAILURE,
                exit_code=1,
                stderr=res.get("error", "Find latest file failed."),
                permission_class=perm_class,
            )

        # Capability: launch_app
        if cap == "launch_app":
            app_name = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            meta = req.metadata or {}
            res = app_launcher.launch_app(
                app=app_name,
                argument=meta.get("argument"),
                directory=cwd,
            )
            if res.get("success"):
                return ExecutionResult(
                    request_id=req.request_id,
                    status=ExecutionStatus.SUCCESS,
                    exit_code=0,
                    stdout=res.get("message", f"Launched {app_name}."),
                    permission_class=perm_class,
                )
            return ExecutionResult(
                request_id=req.request_id,
                status=ExecutionStatus.FAILURE,
                exit_code=1,
                stderr=res.get("error", f"Could not launch {app_name}."),
                permission_class=perm_class,
            )

        # Capability: inspect_process
        if cap == "inspect_process":
            meta = req.metadata or {}
            port = meta.get("port")
            if port:
                port_res = process_manager.inspect_port(int(port))
                return ExecutionResult(
                    request_id=req.request_id,
                    status=ExecutionStatus.SUCCESS,
                    exit_code=0,
                    stdout=json.dumps(port_res, indent=2),
                    permission_class=perm_class,
                )
            procs = process_manager.list_processes(filter_name=str(cmd) if cmd else None)
            lines = [f"• PID {p['pid']}: {p['name']} ({p['memory_mb']} MB)" for p in procs]
            return ExecutionResult(
                request_id=req.request_id,
                status=ExecutionStatus.SUCCESS,
                exit_code=0,
                stdout="\n".join(lines) if lines else "No matching processes found.",
                permission_class=perm_class,
            )

        # Unknown capability
        return ExecutionResult(
            request_id=req.request_id,
            status=ExecutionStatus.DENIED,
            error_type="UNKNOWN_CAPABILITY",
            stderr=f"Unknown desktop capability '{cap}'.",
            permission_class=perm_class,
        )


desktop_executor = DesktopExecutionRegistry()
