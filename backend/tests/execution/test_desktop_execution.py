"""Comprehensive tests for the desktop execution layer and security boundaries."""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.execution.contracts import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    PermissionClass,
)
from app.execution.policy import (
    ExecutionPolicy,
    default_policy,
    redact_secrets,
)
from app.execution.registry import DesktopExecutionRegistry
from app.execution.verification import verify_postcondition
from app.execution.windows.filesystem import ControlledFileSystem
from app.execution.windows.shell import BackgroundJobManager, WindowsShellExecutor


# --- 1. Secret Redaction Tests -----------------------------------------------

def test_redact_secrets_masks_sensitive_patterns():
    raw = (
        "Found google key: AIzaSyD9ABC1234567890123456789012345678 and "
        "OpenAI key: sk-abcdef1234567890abcdef1234567890 and "
        "GitHub token: ghp_123456789012345678901234567890123456 and "
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdef and "
        "password='SuperSecretPassword123!'"
    )
    scrubbed = redact_secrets(raw)
    assert "AIza" not in scrubbed
    assert "sk-" not in scrubbed
    assert "ghp_" not in scrubbed
    assert "SuperSecretPassword123!" not in scrubbed
    assert "[REDACTED_SECRET]" in scrubbed


# --- 2. Path Validation Tests ------------------------------------------------

def test_path_validation_permits_approved_roots():
    policy = ExecutionPolicy()
    ws = Path(r"C:\kirtan\IRIS\backend").resolve()
    ok, err = policy.validate_path(ws, write=False)
    assert ok is True
    assert err is None


def test_path_validation_rejects_unauthorized_traversal():
    policy = ExecutionPolicy()
    # Traversal attempting to escape into another drive or unauthorized directory
    bad_path = Path(r"C:\Windows\System32\cmd.exe")
    ok, err = policy.validate_path(bad_path, write=True)
    assert ok is False
    assert "protected system directory" in err or "outside approved" in err


# --- 3. Permission Classification Tests --------------------------------------

def test_classify_command_read_only():
    policy = ExecutionPolicy()
    cls, reason = policy.classify_command("dir", capability="shell_command")
    assert cls == PermissionClass.CLASS_A_READ_ONLY

    cls, _ = policy.classify_command("git status", capability="shell_command")
    assert cls == PermissionClass.CLASS_A_READ_ONLY

    cls, _ = policy.classify_command("Get-Process", capability="shell_command")
    assert cls == PermissionClass.CLASS_A_READ_ONLY


def test_classify_command_routine_reversible():
    policy = ExecutionPolicy()
    cls, _ = policy.classify_command("pytest tests/", capability="shell_command")
    assert cls == PermissionClass.CLASS_B_ROUTINE

    cls, _ = policy.classify_command("npm run dev", capability="shell_command")
    assert cls == PermissionClass.CLASS_B_ROUTINE


def test_classify_command_sensitive_requires_approval():
    policy = ExecutionPolicy()
    cls, _ = policy.classify_command("pip install requests", capability="shell_command")
    assert cls == PermissionClass.CLASS_C_SENSITIVE

    cls, _ = policy.classify_command("git reset --hard HEAD~1", capability="shell_command")
    assert cls == PermissionClass.CLASS_C_SENSITIVE


def test_classify_command_destructive_blocked():
    policy = ExecutionPolicy()
    cls, _ = policy.classify_command("format C:", capability="shell_command")
    assert cls == PermissionClass.CLASS_D_DESTRUCTIVE

    cls, _ = policy.classify_command("taskkill /f /im svchost.exe", capability="shell_command")
    assert cls == PermissionClass.CLASS_D_DESTRUCTIVE


# --- 4. Approval Token Tests -------------------------------------------------

def test_approval_token_issue_and_verify():
    policy = ExecutionPolicy()
    cmd = "pip install pandas"
    cwd = r"C:\kirtan\IRIS"

    token, prompt = policy.issue_approval_token(cmd, cwd, PermissionClass.CLASS_C_SENSITIVE)
    assert token.startswith("appr_")
    assert "Approval Required" in prompt
    assert token in prompt

    # Verify and consume
    ok, msg = policy.verify_and_consume_token(token, cmd, cwd)
    assert ok is True

    # Replay attempt must fail
    ok_replay, msg_replay = policy.verify_and_consume_token(token, cmd, cwd)
    assert ok_replay is False
    assert "already been consumed" in msg_replay


def test_approval_token_rejects_argument_mismatch():
    policy = ExecutionPolicy()
    token, _ = policy.issue_approval_token("pip install pandas", r"C:\kirtan\IRIS", PermissionClass.CLASS_C_SENSITIVE)

    # Tampered command
    ok, msg = policy.verify_and_consume_token(token, "pip install malicious-pkg", r"C:\kirtan\IRIS")
    assert ok is False
    assert "argument mismatch" in msg


def test_approval_token_rejects_expired():
    policy = ExecutionPolicy()
    token, _ = policy.issue_approval_token("pip install pandas", r"C:\kirtan\IRIS", PermissionClass.CLASS_C_SENSITIVE, ttl_seconds=-1.0)

    ok, msg = policy.verify_and_consume_token(token, "pip install pandas", r"C:\kirtan\IRIS")
    assert ok is False
    assert "expired" in msg


# --- 5. Desktop Execution Registry Tests -------------------------------------

def test_execute_harmless_command():
    registry = DesktopExecutionRegistry()
    req = ExecutionRequest(
        capability="shell_command",
        command="Write-Output 'IRIS Desktop CLI Active'",
        timeout_seconds=10.0,
    )
    res = registry.execute(req)
    assert res.status == ExecutionStatus.SUCCESS
    assert res.exit_code == 0
    assert "IRIS Desktop CLI Active" in res.stdout


def test_execute_blocks_destructive_command():
    policy = ExecutionPolicy(block_class_d=True)
    registry = DesktopExecutionRegistry(policy=policy)
    req = ExecutionRequest(
        capability="shell_command",
        command="format D:",
    )
    res = registry.execute(req)
    assert res.status == ExecutionStatus.DENIED
    assert "blocked by security policy" in res.stderr


def test_execute_sensitive_command_requires_approval():
    policy = ExecutionPolicy(require_approval_for_class_c=True)
    registry = DesktopExecutionRegistry(policy=policy)
    req = ExecutionRequest(
        capability="shell_command",
        command="pip install requests",
    )
    res = registry.execute(req)
    assert res.status == ExecutionStatus.APPROVAL_REQUIRED
    assert res.approval_required is True
    assert res.approval_token is not None
    assert "Approval Required" in res.approval_prompt

    # Authorize with token
    auth_req = ExecutionRequest(
        capability="shell_command",
        command="pip install requests",
        approval_token=res.approval_token,
    )
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Successfully installed requests"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        auth_res = registry.execute(auth_req)
        assert auth_res.status == ExecutionStatus.SUCCESS


def test_execute_denies_unknown_capability():
    registry = DesktopExecutionRegistry()
    req = ExecutionRequest(
        capability="non_existent_capability",
        command="something",
    )
    res = registry.execute(req)
    assert res.status == ExecutionStatus.DENIED
    assert "Unknown desktop capability" in res.stderr


# --- 6. Postcondition Verification Tests -------------------------------------

def test_verification_exit_code_zero():
    res = ExecutionResult(
        request_id="r1",
        status=ExecutionStatus.SUCCESS,
        exit_code=0,
    )
    ok, detail = verify_postcondition({"type": "exit_code_zero"}, res)
    assert ok is True

    res_fail = ExecutionResult(
        request_id="r2",
        status=ExecutionStatus.FAILURE,
        exit_code=1,
    )
    ok_f, detail_f = verify_postcondition({"type": "exit_code_zero"}, res_fail)
    assert ok_f is False


def test_verification_file_exists(tmp_path):
    test_file = tmp_path / "output.txt"
    test_file.write_text("verification sample data", encoding="utf-8")

    res = ExecutionResult(request_id="r3", status=ExecutionStatus.SUCCESS, exit_code=0)
    spec = {"type": "file_exists", "path": str(test_file), "min_size_bytes": 5, "contains_text": "sample"}
    ok, detail = verify_postcondition(spec, res)
    assert ok is True
    assert "Verified: File" in detail


def test_verification_output_contains():
    res = ExecutionResult(
        request_id="r4",
        status=ExecutionStatus.SUCCESS,
        stdout="Server listening on port 8000",
    )
    ok, detail = verify_postcondition({"type": "output_contains", "pattern": r"port \d+"}, res)
    assert ok is True


# --- 7. Background Job Manager Tests -----------------------------------------

def test_background_job_manager_start_and_cancel():
    mgr = BackgroundJobManager()
    # Start a slow PowerShell loop in background
    job = mgr.start_job(
        command="for ($i=0; $i -lt 10; $i++) { Write-Output \"Tick $i\"; Start-Sleep -Milliseconds 200 }",
        cwd=r"C:\kirtan\IRIS",
    )
    assert job.job_id.startswith("job_")
    assert job.status == "RUNNING"
    assert job.pid is not None

    info = None
    for _ in range(30):
        time.sleep(0.1)
        info = mgr.get_job(job.job_id)
        if info and "Tick" in info.output_preview:
            break

    assert info is not None
    assert "Tick" in info.output_preview

    # Cancel the job
    cancelled = mgr.cancel_job(job.job_id)
    assert cancelled is True

    cancelled_info = mgr.get_job(job.job_id)
    assert cancelled_info.status == "CANCELLED"


# --- 8. Controlled Filesystem Tests ------------------------------------------

def test_controlled_fs_list_and_read(tmp_path):
    policy = ExecutionPolicy(allowed_roots=[tmp_path])
    fs = ControlledFileSystem(policy=policy)

    f1 = tmp_path / "hello.txt"
    f1.write_text("Hello IRIS Desktop", encoding="utf-8")

    list_res = fs.list_directory(str(tmp_path))
    assert list_res["success"] is True
    assert list_res["count"] == 1
    assert list_res["entries"][0]["name"] == "hello.txt"

    read_res = fs.read_file(str(f1))
    assert read_res["success"] is True
    assert read_res["content"] == "Hello IRIS Desktop"


def test_controlled_fs_find_latest_file(tmp_path):
    policy = ExecutionPolicy(allowed_roots=[tmp_path])
    fs = ControlledFileSystem(policy=policy)

    old_f = tmp_path / "report_old.pdf"
    old_f.write_text("old pdf", encoding="utf-8")
    time.sleep(0.05)
    new_f = tmp_path / "report_new.pdf"
    new_f.write_text("new pdf", encoding="utf-8")

    latest_res = fs.find_latest_file(str(tmp_path), extension="pdf")
    assert latest_res["success"] is True
    assert latest_res["name"] == "report_new.pdf"
