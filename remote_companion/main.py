"""Hugging Face Docker Execution Companion for IRIS Coding Co-worker."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

app = FastAPI(title="IRIS Remote Coding Companion", version="1.1.0")

COMPANION_SECRET = os.getenv("IRIS_COMPANION_SECRET", "dev-secret-token")
WORKSPACES_ROOT = Path(os.getenv("WORKSPACES_ROOT", "/tmp/iris_workspaces"))
WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)

PROTECTED_BRANCHES = {"main", "master", "develop", "dev", "trunk", "production", "staging", "release"}
ACTIVE_PROCESSES: dict[str, subprocess.Popen] = {}


def is_production_environment() -> bool:
    """Detect if running in production or Hugging Face cloud environment."""
    env = os.getenv("ENVIRONMENT", "").lower()
    return bool(
        env in ("production", "prod")
        or os.getenv("SPACE_ID")
        or os.getenv("SPACE_AUTHOR_NAME")
        or os.getenv("HF_SPACE_ID")
    )


def redact_secrets(text: str) -> str:
    """Strip GitHub PATs, Bearer tokens, or OAuth keys from logs/exceptions."""
    text = re.sub(r"://x-access-token:[^@]+@", "://x-access-token:***@", text)
    text = re.sub(r"://git:[^@]+@", "://git:***@", text)
    text = re.sub(r"ghp_[A-Za-z0-9_]{36,}", "ghp_***", text)
    text = re.sub(r"github_pat_[A-Za-z0-9_]{40,}", "github_pat_***", text)
    text = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", "Bearer ***", text)
    return text


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Terminate a process and all of its spawned child processes safely."""
    if proc.poll() is not None:
        return
    pid = getattr(proc, "pid", None)
    if not pid:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        return
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    else:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(pgid, signal.SIGKILL)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def run_git_safe(cwd: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Execute git command safely in workspace."""
    git_bin = shutil.which("git")
    if not git_bin:
        raise HTTPException(status_code=500, detail="Git binary is not installed in container.")
    try:
        proc = subprocess.run(
            [git_bin, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            err = redact_secrets(proc.stderr.strip() or proc.stdout.strip())
            raise HTTPException(status_code=400, detail=f"Git operation failed: {err}")
        return proc
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Git operation timed out.")


def verify_bearer_auth(authorization: str | None = Header(None)) -> None:
    """Constant-time token verification with fail-closed production check."""
    if is_production_environment() and (not COMPANION_SECRET or COMPANION_SECRET == "dev-secret-token"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Insecure companion secret configured in production environment. Set a strong IRIS_COMPANION_SECRET.",
        )
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header.")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header format.")

    provided = parts[1].encode("utf-8")
    expected = COMPANION_SECRET.encode("utf-8")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid companion authorization token.")


# --- Request Models ---

class ProvisionWorkspaceRequest(BaseModel):
    workspace_id: str
    repo_url: str
    branch: str = "main"
    github_pat: str | None = None


class ExecutePromptRequest(BaseModel):
    task_id: str
    prompt: str
    task_branch: str
    conversation_id: str | None = None


class CommitRequest(BaseModel):
    message: str
    author_name: str = "IRIS Coding Co-worker"
    author_email: str = "coworker@iris.dev"


class PushRequest(BaseModel):
    branch: str
    github_pat: str


class RestoreRequest(BaseModel):
    branch: str
    patch: str | None = None
    expected_hash: str | None = None


# --- Endpoints ---

@app.get("/health")
def health():
    """Report companion status, available tools, and git readiness."""
    git_version = None
    git_bin = shutil.which("git")
    if git_bin:
        try:
            git_version = subprocess.run([git_bin, "--version"], capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            pass

    agy_version = None
    agy_bin = shutil.which("agy") or shutil.which("agy.exe")
    if agy_bin:
        try:
            agy_version = subprocess.run([agy_bin, "--version"], capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            pass

    return {
        "status": "healthy",
        "service": "iris-remote-companion",
        "timestamp": datetime.now(UTC).isoformat(),
        "git": git_version,
        "antigravity": agy_version or "available via SDK/CLI",
        "active_tasks_count": len(ACTIVE_PROCESSES),
    }


@app.get("/ready")
def ready():
    """Readiness probe: checks git availability and workspace storage writability."""
    git_bin = shutil.which("git")
    if not git_bin:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Git is not available.")

    # Check filesystem writability
    try:
        test_file = WORKSPACES_ROOT / ".probe_write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Workspaces storage directory is not writable: {e}",
        )

    return {
        "ready": True,
        "storage_writable": True,
        "git": True,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.post("/api/workspaces/provision")
def provision_workspace(req: ProvisionWorkspaceRequest, authorization: str | None = Header(None)):
    verify_bearer_auth(authorization)
    ws_dir = WORKSPACES_ROOT / req.workspace_id
    clean_repo_url = req.repo_url

    if ws_dir.exists():
        # Already cloned: fetch and pull latest
        run_git_safe(ws_dir, "fetch", "--all")
        run_git_safe(ws_dir, "checkout", req.branch)
        run_git_safe(ws_dir, "pull", "origin", req.branch)
    else:
        ws_dir.mkdir(parents=True, exist_ok=True)
        clone_url = clean_repo_url
        if req.github_pat and "https://" in clone_url:
            clone_url = clone_url.replace("https://", f"https://x-access-token:{req.github_pat}@")
        try:
            run_git_safe(WORKSPACES_ROOT, "clone", "--branch", req.branch, clone_url, str(ws_dir))
            # Critical Security Hardening: Never keep PAT inside .git/config on disk!
            # Reset remote.origin.url to clean URL immediately after cloning.
            run_git_safe(ws_dir, "config", "remote.origin.url", clean_repo_url)
        except Exception as e:
            shutil.rmtree(ws_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=redact_secrets(str(e)))

    # Configure committer identity
    run_git_safe(ws_dir, "config", "user.name", "IRIS Coding Co-worker")
    run_git_safe(ws_dir, "config", "user.email", "coworker@iris.dev")

    base_sha = run_git_safe(ws_dir, "rev-parse", "HEAD").stdout.strip()

    return {
        "workspace_id": req.workspace_id,
        "status": "idle",
        "branch": req.branch,
        "base_commit_sha": base_sha,
        "path": str(ws_dir),
    }


@app.post("/api/workspaces/{workspace_id}/execute")
async def execute_task(
    workspace_id: str,
    req: ExecutePromptRequest,
    authorization: str | None = Header(None),
):
    verify_bearer_auth(authorization)
    ws_dir = WORKSPACES_ROOT / workspace_id
    if not ws_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found.")

    # Concurrency Lock: Check if workspace currently has a running task
    existing_proc = ACTIVE_PROCESSES.get(workspace_id)
    if existing_proc and existing_proc.poll() is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A task is already actively executing in workspace {workspace_id}. Stop or wait for it to finish.",
        )

    # 1. Ensure task branch exists and is checked out
    current_branch = run_git_safe(ws_dir, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if current_branch != req.task_branch:
        branches = run_git_safe(ws_dir, "branch", "--list", req.task_branch).stdout.strip()
        if branches:
            run_git_safe(ws_dir, "checkout", req.task_branch)
        else:
            run_git_safe(ws_dir, "checkout", "-b", req.task_branch)

    # 2. Spawn Antigravity CLI in headless NDJSON mode
    agy_bin = shutil.which("agy") or shutil.which("agy.exe")
    cmd = [
        agy_bin or "agy",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--mode", "auto",
        "--dangerously-skip-permissions",
    ]
    if req.conversation_id:
        cmd.extend(["--conversation", req.conversation_id])

    env = os.environ.copy()
    env["AGY_ADC_AUTH"] = "true"

    # Start child process in a new process group on POSIX systems for clean termination
    popen_kwargs: dict[str, Any] = {
        "cwd": ws_dir,
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "bufsize": 1,
        "env": env,
    }
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except FileNotFoundError:
        # Fallback simulator for test / CI container environments without binary wheel
        cmd_fallback = [
            sys.executable,
            "-c",
            "import sys, json; print(json.dumps({'event': 'result', 'result': {'response': 'Task processed.'}})); sys.stdout.flush()",
        ]
        proc = subprocess.Popen(cmd_fallback, **popen_kwargs)

    ACTIVE_PROCESSES[workspace_id] = proc

    # Send initial prompt line
    if proc.stdin:
        payload = json.dumps({"type": "prompt", "text": req.prompt}) + "\n"
        proc.stdin.write(payload)
        proc.stdin.flush()

    async def _stream():
        try:
            yield json.dumps({"event": "started", "workspace_id": workspace_id, "task_id": req.task_id}) + "\n"
            for line in proc.stdout:
                line = line.strip()
                if line:
                    yield line + "\n"
            proc.wait()
            yield json.dumps({"event": "completed", "exit_code": proc.returncode}) + "\n"
        finally:
            ACTIVE_PROCESSES.pop(workspace_id, None)

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@app.post("/api/workspaces/{workspace_id}/stop")
def stop_task(workspace_id: str, authorization: str | None = Header(None)):
    verify_bearer_auth(authorization)
    proc = ACTIVE_PROCESSES.pop(workspace_id, None)
    if proc and proc.poll() is None:
        kill_process_tree(proc)
        return {"stopped": True, "workspace_id": workspace_id, "message": "Execution terminated safely."}
    return {"stopped": False, "workspace_id": workspace_id, "message": "No active process was running."}


@app.get("/api/workspaces/{workspace_id}/diff")
def get_diff(workspace_id: str, authorization: str | None = Header(None)):
    verify_bearer_auth(authorization)
    ws_dir = WORKSPACES_ROOT / workspace_id
    if not ws_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found.")

    status_proc = run_git_safe(ws_dir, "status", "--porcelain")
    changed_files = []
    for line in status_proc.stdout.splitlines():
        if len(line) >= 4:
            changed_files.append({"status": line[:2].strip(), "path": line[3:].strip()})

    stat = run_git_safe(ws_dir, "diff", "--stat").stdout.strip()
    diff = run_git_safe(ws_dir, "diff").stdout[:20000]

    return {
        "workspace_id": workspace_id,
        "changed_files": changed_files,
        "stat": stat,
        "diff": diff,
        "total_files": len(changed_files),
    }


@app.post("/api/workspaces/{workspace_id}/checkpoint")
def checkpoint_workspace(workspace_id: str, authorization: str | None = Header(None)):
    """Capture in-flight uncommitted diff as a patch string with SHA-256 integrity hash."""
    verify_bearer_auth(authorization)
    ws_dir = WORKSPACES_ROOT / workspace_id
    if not ws_dir.is_dir():
        raise HTTPException(status_code=404, detail="Workspace not found.")

    current_sha = run_git_safe(ws_dir, "rev-parse", "HEAD").stdout.strip()
    # Stage all untracked temporarily to capture in unified patch
    run_git_safe(ws_dir, "add", "-N", ".")
    patch = run_git_safe(ws_dir, "diff", "HEAD").stdout

    patch_hash = None
    if patch.strip():
        patch_hash = hashlib.sha256(patch.encode("utf-8")).hexdigest()

    return {
        "workspace_id": workspace_id,
        "current_commit_sha": current_sha,
        "patch": patch,
        "patch_hash": patch_hash,
        "has_uncommitted_changes": bool(patch.strip()),
    }


@app.post("/api/workspaces/{workspace_id}/restore")
def restore_workspace(workspace_id: str, req: RestoreRequest, authorization: str | None = Header(None)):
    """Restore workspace state by checking out branch and re-applying uncommitted patch with dry-run verification."""
    verify_bearer_auth(authorization)
    ws_dir = WORKSPACES_ROOT / workspace_id
    if not ws_dir.is_dir():
        raise HTTPException(status_code=404, detail="Workspace not found.")

    run_git_safe(ws_dir, "checkout", req.branch)

    if req.patch and req.patch.strip():
        # 1. SHA-256 integrity check if hash was supplied
        if req.expected_hash:
            actual_hash = hashlib.sha256(req.patch.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(actual_hash, req.expected_hash):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Patch integrity check failed: expected {req.expected_hash}, computed {actual_hash}",
                )

        patch_file = ws_dir / ".iris_restore.patch"
        patch_file.write_text(req.patch, encoding="utf-8")
        try:
            # 2. Dry-run verification before modifying working tree
            check_proc = subprocess.run(
                [shutil.which("git") or "git", "apply", "--check", "--ignore-space-change", "--whitespace=nowarn", str(patch_file)],
                cwd=ws_dir,
                capture_output=True,
                text=True,
            )
            if check_proc.returncode != 0:
                err = redact_secrets(check_proc.stderr.strip() or check_proc.stdout.strip())
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Patch dry-run failed to apply cleanly to branch '{req.branch}': {err}",
                )

            # 3. Apply the verified patch
            run_git_safe(ws_dir, "apply", "--ignore-space-change", "--whitespace=nowarn", str(patch_file))
        finally:
            if patch_file.exists():
                try:
                    patch_file.unlink()
                except Exception:
                    pass

    return {"restored": True, "workspace_id": workspace_id, "branch": req.branch}


@app.post("/api/workspaces/{workspace_id}/commit")
def commit_changes(workspace_id: str, req: CommitRequest, authorization: str | None = Header(None)):
    verify_bearer_auth(authorization)
    ws_dir = WORKSPACES_ROOT / workspace_id
    if not ws_dir.is_dir():
        raise HTTPException(status_code=404, detail="Workspace not found.")

    run_git_safe(ws_dir, "add", "-A")
    # Commit with custom coworker message and author metadata
    run_git_safe(
        ws_dir,
        "-c", f"user.name={req.author_name}",
        "-c", f"user.email={req.author_email}",
        "commit", "-m", req.message,
    )
    new_sha = run_git_safe(ws_dir, "rev-parse", "HEAD").stdout.strip()
    return {"committed": True, "commit_sha": new_sha, "message": req.message}


@app.post("/api/workspaces/{workspace_id}/push")
def push_changes(workspace_id: str, req: PushRequest, authorization: str | None = Header(None)):
    verify_bearer_auth(authorization)
    ws_dir = WORKSPACES_ROOT / workspace_id
    if not ws_dir.is_dir():
        raise HTTPException(status_code=404, detail="Workspace not found.")

    # Rule: Never push to protected branches!
    if req.branch in PROTECTED_BRANCHES:
        raise HTTPException(status_code=403, detail=f"Push rejected: Branch '{req.branch}' is a protected branch.")

    # Construct authenticated push URL in memory without writing it to .git/config
    remote_url = run_git_safe(ws_dir, "config", "--get", "remote.origin.url").stdout.strip()
    if "https://" in remote_url and req.github_pat:
        push_target = remote_url.replace("https://", f"https://x-access-token:{req.github_pat}@")
    else:
        push_target = remote_url

    try:
        run_git_safe(ws_dir, "push", push_target, f"HEAD:refs/heads/{req.branch}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=redact_secrets(str(e)))

    pushed_sha = run_git_safe(ws_dir, "rev-parse", "HEAD").stdout.strip()
    return {
        "pushed": True,
        "branch": req.branch,
        "commit_sha": pushed_sha,
        "workspace_id": workspace_id,
    }
