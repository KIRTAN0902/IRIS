"""Windows PowerShell execution and background job management."""

from __future__ import annotations

import collections
import os
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.execution.contracts import JobInfo

logger = get_logger("iris.execution.windows.shell")

MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB per stream limit


class WindowsShellExecutor:
    """Synchronous PowerShell command execution with strict timeouts and output limits."""

    def __init__(self, default_workspace: str = r"C:\kirtan\IRIS") -> None:
        self.default_workspace = default_workspace

    def execute_sync(
        self,
        command: str | list[str],
        cwd: str | None = None,
        timeout_seconds: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str, int]:
        """Execute a command synchronously via PowerShell.

        Returns (exit_code, stdout, stderr, duration_ms).
        """
        work_dir = cwd.strip() if cwd and cwd.strip() else self.default_workspace
        if not os.path.exists(work_dir):
            work_dir = str(Path.home())

        if isinstance(command, list):
            cmd_args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"] + command
        else:
            cmd_args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        start_time = time.perf_counter()
        try:
            res = subprocess.run(
                cmd_args,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                encoding="utf-8",
                errors="replace",
                env=merged_env,
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Enforce output length bounds
            out = res.stdout or ""
            err = res.stderr or ""
            if len(out) > MAX_OUTPUT_BYTES:
                out = out[:MAX_OUTPUT_BYTES] + "\n... [stdout truncated by IRIS security limit]"
            if len(err) > MAX_OUTPUT_BYTES:
                err = err[:MAX_OUTPUT_BYTES] + "\n... [stderr truncated by IRIS security limit]"

            return res.returncode, out, err, duration_ms

        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning("Command timed out after %ss: %s", timeout_seconds, command)
            partial_out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            return -1, partial_out, f"Command timed out after {timeout_seconds} seconds.", duration_ms

        except Exception as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("Command execution error: %s", exc)
            return -1, "", str(exc), duration_ms


class BackgroundJobManager:
    """Tracks and manages asynchronous or long-running processes (e.g. dev servers, builds)."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start_job(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> JobInfo:
        """Spawn a non-blocking background job and capture output in a ring buffer."""
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        work_dir = cwd.strip() if cwd and cwd.strip() else r"C:\kirtan\IRIS"
        if not os.path.exists(work_dir):
            work_dir = str(Path.home())

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        cmd_args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]

        proc = subprocess.Popen(
            cmd_args,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=merged_env,
        )

        buffer = collections.deque(maxlen=300)

        record = {
            "job_id": job_id,
            "command": command,
            "cwd": work_dir,
            "proc": proc,
            "pid": proc.pid,
            "buffer": buffer,
            "started_at": datetime.now(timezone.utc),
            "ended_at": None,
            "exit_code": None,
            "status": "RUNNING",
        }

        with self._lock:
            self._jobs[job_id] = record

        # Spawn background reader thread
        def _read_output() -> None:
            try:
                if proc.stdout:
                    for line in iter(proc.stdout.readline, ""):
                        buffer.append(line)
                    proc.stdout.close()
            except Exception:
                pass
            finally:
                proc.wait()
                record["exit_code"] = proc.returncode
                record["ended_at"] = datetime.now(timezone.utc)
                record["status"] = "COMPLETED" if proc.returncode == 0 else "FAILED"

        t = threading.Thread(target=_read_output, daemon=True)
        t.start()

        return JobInfo(
            job_id=job_id,
            command=command,
            pid=proc.pid,
            status="RUNNING",
            started_at=record["started_at"],
            working_dir=work_dir,
            output_preview="Job launched in background.",
        )

    def get_job(self, job_id: str) -> JobInfo | None:
        """Inspect a background job's status and recent output lines."""
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return None

            proc: subprocess.Popen = rec["proc"]
            if rec["status"] == "RUNNING" and proc.poll() is not None:
                rec["exit_code"] = proc.returncode
                rec["ended_at"] = datetime.now(timezone.utc)
                rec["status"] = "COMPLETED" if proc.returncode == 0 else "FAILED"

            preview = "".join(list(rec["buffer"])[-20:])

            return JobInfo(
                job_id=job_id,
                command=rec["command"],
                pid=rec["pid"],
                status=rec["status"],
                started_at=rec["started_at"],
                ended_at=rec["ended_at"],
                exit_code=rec["exit_code"],
                working_dir=rec["cwd"],
                output_preview=preview,
            )

    def list_jobs(self) -> list[JobInfo]:
        """List all tracked jobs."""
        with self._lock:
            job_ids = list(self._jobs.keys())

        result: list[JobInfo] = []
        for jid in job_ids:
            info = self.get_job(jid)
            if info:
                result.append(info)
        return result

    def cancel_job(self, job_id: str) -> bool:
        """Terminate a running background process and its children."""
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return False

            proc: subprocess.Popen = rec["proc"]
            if rec["status"] != "RUNNING":
                return True  # Already finished

            try:
                # Force kill process tree on Windows
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

            rec["status"] = "CANCELLED"
            rec["ended_at"] = datetime.now(timezone.utc)
            return True


# Global instances
windows_shell = WindowsShellExecutor()
job_manager = BackgroundJobManager()
